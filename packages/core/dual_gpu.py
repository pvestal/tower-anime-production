"""Dual-GPU routing — manages both GPUs for keyframes, video, and exploration.

Both GPUs can run any task (keyframes or video). Smart routing avoids model
swap overhead by preferring the GPU that already has the right model loaded.

GPU inventory:
  - NVIDIA RTX 3060 (12GB) on :8188 — default keyframe GPU
  - AMD RX 9070 XT (16GB) on :8189 — default video GPU

When DUAL_VIDEO_MODE=1, both run video (DaSiWa Q4 GGUF) concurrently.
Key constraint: 3060 has ~0.6GB headroom with DaSiWa Q4, so motion LoRAs
are skipped on that GPU. DaSiWa's distillation compensates.
"""

import asyncio
import enum
import json
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)

COMFYUI_NVIDIA_URL = "http://127.0.0.1:8188"
COMFYUI_AMD_URL = "http://127.0.0.1:8189"

# Minimum free VRAM on 3060 for DaSiWa Q4 (MB)
_MIN_FREE_VRAM_MB = 10000


class GpuMode(enum.Enum):
    KEYFRAME = "keyframe"
    VIDEO = "video"
    TRANSITIONING = "transitioning"


# Track current 3060 mode
_3060_mode = GpuMode.KEYFRAME
_mode_lock = asyncio.Lock()


def is_dual_video_enabled() -> bool:
    """Check if dual-GPU video mode is enabled via environment."""
    return os.getenv("DUAL_VIDEO_MODE", "0") == "1"


def get_video_targets() -> list[str]:
    """Return list of ComfyUI URLs available for video generation."""
    if is_dual_video_enabled() and _3060_mode == GpuMode.VIDEO:
        return [COMFYUI_AMD_URL, COMFYUI_NVIDIA_URL]
    return [COMFYUI_AMD_URL]


def get_3060_mode() -> GpuMode:
    """Return current 3060 GPU mode."""
    return _3060_mode


def _free_comfyui_vram(url: str) -> bool:
    """Ask a ComfyUI instance to unload models and free VRAM."""
    try:
        payload = json.dumps({"unload_models": True, "free_memory": True}).encode()
        req = urllib.request.Request(
            f"{url}/free",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        logger.warning(f"Failed to free VRAM on {url}: {e}")
        return False


def _get_nvidia_free_mb() -> int | None:
    """Query nvidia-smi for free VRAM in MB."""
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        return int(result.stdout.strip().split("\n")[0].strip())
    except Exception:
        return None


async def swap_3060_to_video() -> bool:
    """Free 3060 VRAM and prepare for video generation.

    Returns True if 3060 is ready for video, False if swap failed.
    """
    global _3060_mode
    async with _mode_lock:
        if _3060_mode == GpuMode.VIDEO:
            return True

        _3060_mode = GpuMode.TRANSITIONING
        logger.info("Swapping 3060 from KEYFRAME → VIDEO mode")

        # Free VRAM
        if not _free_comfyui_vram(COMFYUI_NVIDIA_URL):
            _3060_mode = GpuMode.KEYFRAME
            return False

        # Wait for models to unload
        await asyncio.sleep(2)

        # Verify VRAM is available
        free_mb = _get_nvidia_free_mb()
        if free_mb is not None and free_mb < _MIN_FREE_VRAM_MB:
            logger.warning(
                f"3060 only has {free_mb}MB free after unload, "
                f"need {_MIN_FREE_VRAM_MB}MB — swap failed"
            )
            _3060_mode = GpuMode.KEYFRAME
            return False

        _3060_mode = GpuMode.VIDEO
        logger.info(f"3060 swapped to VIDEO mode ({free_mb}MB free)")
        return True


async def swap_3060_to_keyframe() -> bool:
    """Return 3060 to keyframe mode after video generation."""
    global _3060_mode
    async with _mode_lock:
        if _3060_mode == GpuMode.KEYFRAME:
            return True

        logger.info("Swapping 3060 from VIDEO → KEYFRAME mode")
        _free_comfyui_vram(COMFYUI_NVIDIA_URL)
        _3060_mode = GpuMode.KEYFRAME
        logger.info("3060 swapped back to KEYFRAME mode")
        return True


def gpu_label_for_url(comfyui_url: str) -> str:
    """Return a tracking label for the GPU serving a given ComfyUI URL."""
    if "8188" in comfyui_url:
        return "nvidia_q4"
    return "amd_q4"


def should_skip_motion_lora(comfyui_url: str) -> bool:
    """Whether to skip motion LoRAs for a given GPU (3060 has no headroom)."""
    return "8188" in comfyui_url


# ---------------------------------------------------------------------------
# Smart routing: pick the best GPU for a task based on queue + model state
# ---------------------------------------------------------------------------

def _get_queue_depth(url: str) -> int:
    """Return number of running + pending jobs on a ComfyUI instance."""
    try:
        req = urllib.request.Request(f"{url}/queue")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        return len(data.get("queue_running", [])) + len(data.get("queue_pending", []))
    except Exception:
        return 999  # Unreachable → treat as fully busy


def get_best_gpu_for_task(task_type: str = "keyframe") -> str:
    """Pick the best available GPU URL for a given task type.

    Arbiter rules — avoid model swaps that kill throughput:
      - Keyframes ALWAYS go to 3060 (SDXL loaded). Never overflow to 9070
        because swapping from DaSiWa → SDXL takes minutes and causes timeouts.
      - Video prefers 9070 (DaSiWa loaded). Overflows to 3060 when 9070 is
        saturated — both GPUs keep DaSiWa loaded with --lowvram so no swap.

    Args:
        task_type: "keyframe" or "video"

    Returns:
        ComfyUI URL string (e.g. "http://127.0.0.1:8188")
    """
    if task_type == "keyframe":
        # Keyframes always stay on 3060 — no model swap risk
        return COMFYUI_NVIDIA_URL

    # Video: prefer 9070, overflow to 3060 based on queue depth
    amd_q = _get_queue_depth(COMFYUI_AMD_URL)
    nvidia_q = _get_queue_depth(COMFYUI_NVIDIA_URL)

    # Primary (AMD) idle → use it
    if amd_q == 0:
        return COMFYUI_AMD_URL

    # AMD busy, 3060 idle → overflow video to 3060
    if nvidia_q == 0:
        logger.info(
            f"Smart routing: video → 3060 overflow "
            f"(9070 queue={amd_q}, 3060 idle)"
        )
        return COMFYUI_NVIDIA_URL

    # Both busy → pick shorter queue
    if amd_q <= nvidia_q:
        return COMFYUI_AMD_URL
    logger.info(
        f"Smart routing: video → 3060 overflow "
        f"(9070 queue={amd_q} > 3060 queue={nvidia_q})"
    )
    return COMFYUI_NVIDIA_URL


def get_keyframe_targets() -> list[str]:
    """Return list of ComfyUI URLs available for keyframe generation.

    Both GPUs can do keyframes. Returns both when the system is in
    keyframe phase, or just the nvidia when AMD is busy with video.
    """
    amd_q = _get_queue_depth(COMFYUI_AMD_URL)
    # If AMD has video jobs running, don't send keyframes there
    if amd_q > 0:
        return [COMFYUI_NVIDIA_URL]
    return [COMFYUI_NVIDIA_URL, COMFYUI_AMD_URL]
