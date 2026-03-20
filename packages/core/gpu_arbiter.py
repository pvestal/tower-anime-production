"""GPU Arbiter — cross-service coordination for AMD RX 9070 XT resources.

Manages VRAM contention between Ollama (vision QC, embeddings, chat) and
ComfyUI-ROCm (video generation) on the shared AMD GPU.

Key responsibilities:
1. Ollama model lifecycle (pin/warm/unload)
2. AMD VRAM budget tracking
3. Claim/release system for exclusive GPU tasks
4. Cross-service status for Echo Brain integration
"""

import asyncio
import json
import logging
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from .config import OLLAMA_URL, COMFYUI_VIDEO_URL, VISION_MODEL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMBED_MODEL = "nomic-embed-text"

# VRAM budget (MB) — AMD RX 9070 XT 16GB
AMD_TOTAL_VRAM_MB = 16384
VRAM_BUDGET = {
    EMBED_MODEL: 350,         # Always pinned
    VISION_MODEL: 8200,       # On-demand for vision QC
    "comfyui_rocm": 10000,    # ComfyUI-ROCm generation
    "headroom": 2000,         # OS/drivers
}


class ClaimType(str, Enum):
    VISION_REVIEW = "vision_review"
    COMFYUI_ROCM = "comfyui_rocm"
    ECHO_REASONING = "echo_reasoning"
    ECHO_VISION = "echo_vision"


@dataclass
class GpuClaim:
    claim_type: ClaimType
    claimed_at: datetime
    estimated_duration_s: int
    caller: str  # service name
    model_needed: Optional[str] = None


@dataclass
class ArbiterState:
    """In-memory state of the GPU arbiter."""
    active_claims: dict[str, GpuClaim] = field(default_factory=dict)
    embed_pinned: bool = False
    vision_model_warm: bool = False
    last_ollama_check: float = 0.0
    loaded_models: list[str] = field(default_factory=list)
    ollama_vram_mb: int = 0
    comfyui_rocm_busy: bool = False
    initialized: bool = False


# Module-level singleton
_state = ArbiterState()

# Lock for claim operations
_claim_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Ollama model lifecycle helpers
# ---------------------------------------------------------------------------

def _ollama_request(endpoint: str, payload: dict | None = None,
                    method: str = "GET", timeout: int = 10) -> dict | None:
    """Low-level Ollama API call."""
    try:
        url = f"{OLLAMA_URL}{endpoint}"
        if payload:
            data = json.dumps(payload).encode()
            req = urllib.request.Request(url, data=data,
                                        headers={"Content-Type": "application/json"},
                                        method=method)
        else:
            req = urllib.request.Request(url, method=method)
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read())
    except Exception as e:
        logger.warning(f"Ollama request failed ({endpoint}): {e}")
        return None


def _get_loaded_models() -> list[dict]:
    """Query Ollama for currently loaded models + VRAM."""
    data = _ollama_request("/api/ps")
    if not data:
        return []
    return data.get("models", [])


def _is_model_loaded(model_name: str) -> bool:
    """Check if a specific model is currently loaded in Ollama."""
    for m in _get_loaded_models():
        if model_name in m.get("name", ""):
            return True
    return False


def _set_keep_alive(model: str, keep_alive: str | int = -1,
                    timeout: int = 120) -> bool:
    """Load/pin a model with a specific keep_alive duration.

    keep_alive: -1 = forever, "30m" = 30 minutes, 0 = unload immediately.
    Uses /api/embed for embedding models, /api/generate for generative models.
    """
    # Embedding models need /api/embed endpoint
    if "embed" in model:
        payload = {
            "model": model,
            "input": "ping",
            "keep_alive": keep_alive,
        }
        endpoint = "/api/embed"
    else:
        payload = {
            "model": model,
            "prompt": "",
            "stream": False,
            "keep_alive": keep_alive,
        }
        endpoint = "/api/generate"

    try:
        url = f"{OLLAMA_URL}{endpoint}"
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data,
                                    headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=timeout)
        logger.info(f"Ollama model '{model}' keep_alive set to {keep_alive} via {endpoint}")
        return True
    except Exception as e:
        logger.error(f"Failed to set keep_alive for '{model}': {e}")
        return False


def _unload_model(model: str) -> bool:
    """Unload a model from Ollama VRAM."""
    return _set_keep_alive(model, keep_alive=0, timeout=15)


def _get_amd_free_vram_mb() -> int | None:
    """Read AMD GPU free VRAM from sysfs. Returns MB or None if unavailable."""
    try:
        from pathlib import Path as _Path
        drm_dir = _Path("/sys/class/drm")
        for card_dir in sorted(drm_dir.glob("card[0-9]")):
            device_dir = card_dir / "device"
            vendor_file = device_dir / "vendor"
            if vendor_file.exists() and vendor_file.read_text().strip() == "0x1002":
                total = int((device_dir / "mem_info_vram_total").read_text().strip())
                used = int((device_dir / "mem_info_vram_used").read_text().strip())
                return (total - used) // (1024 * 1024)
    except Exception:
        pass
    return None


def _free_comfyui_rocm_vram() -> bool:
    """Ask ComfyUI-ROCm (:8189) to unload models and free VRAM."""
    try:
        payload = json.dumps({"unload_models": True, "free_memory": True}).encode()
        req = urllib.request.Request(
            f"{COMFYUI_VIDEO_URL}/free",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        logger.info("ComfyUI-ROCm models freed from VRAM")
        return True
    except Exception as e:
        logger.warning(f"Failed to free ComfyUI-ROCm VRAM: {e}")
        return False


def _check_comfyui_rocm_busy() -> bool:
    """Check if ComfyUI-ROCm (:8189) has active/pending work."""
    try:
        req = urllib.request.Request(f"{COMFYUI_VIDEO_URL}/queue")
        resp = urllib.request.urlopen(req, timeout=3)
        data = json.loads(resp.read())
        running = data.get("queue_running", [])
        pending = data.get("queue_pending", [])
        return len(running) > 0 or len(pending) > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Arbiter core operations
# ---------------------------------------------------------------------------

async def initialize():
    """One-time startup: pin embedding model, refresh state.

    Model pinning runs in background to avoid blocking app startup.
    """
    if _state.initialized:
        return

    logger.info("GPU Arbiter initializing...")
    _state.initialized = True

    # Pin embedding model in background — don't block startup
    asyncio.create_task(_background_init())

    logger.info("GPU Arbiter initialized (model pinning in background)")


async def _background_init():
    """Background task to pin models after startup."""
    try:
        # Small delay to let the app finish starting
        await asyncio.sleep(2)

        # Check AMD VRAM first — ComfyUI-ROCm may be holding most of it
        amd_free = await asyncio.to_thread(_get_amd_free_vram_mb)
        if amd_free is not None and amd_free < 1000:
            logger.warning(
                f"AMD VRAM too low ({amd_free}MB free) to pin {EMBED_MODEL}. "
                f"ComfyUI-ROCm likely holding VRAM. Will retry on next vision warm."
            )
            await refresh_state()
            return

        # Ollama Vulkan can only serve one model at a time — unload others first
        models = await asyncio.to_thread(_get_loaded_models)
        for m in models:
            name = m.get("name", "")
            if EMBED_MODEL not in name:
                logger.info(f"Unloading {name} to make room for {EMBED_MODEL} pin...")
                await asyncio.to_thread(_unload_model, name)
                await asyncio.sleep(2)

        success = await asyncio.to_thread(_set_keep_alive, EMBED_MODEL, -1, 300)
        _state.embed_pinned = success
        if success:
            logger.info(f"Pinned {EMBED_MODEL} permanently (~{VRAM_BUDGET[EMBED_MODEL]}MB)")
        else:
            logger.warning(f"Failed to pin {EMBED_MODEL} — embeddings may have cold starts")

        await refresh_state()
    except Exception as e:
        logger.error(f"Background arbiter init failed: {e}")


async def refresh_state():
    """Update arbiter's view of the GPU world. Cheap — call often."""
    now = time.time()
    # Throttle to once per 5 seconds
    if now - _state.last_ollama_check < 5:
        return
    _state.last_ollama_check = now

    try:
        models = await asyncio.to_thread(_get_loaded_models)
        _state.loaded_models = [m.get("name", "") for m in models]
        _state.ollama_vram_mb = sum(
            m.get("size_vram", 0) // (1024 * 1024) for m in models
        )
        _state.vision_model_warm = any(
            VISION_MODEL in name for name in _state.loaded_models
        )
        _state.comfyui_rocm_busy = await asyncio.to_thread(_check_comfyui_rocm_busy)
    except Exception as e:
        logger.warning(f"Arbiter state refresh failed: {e}")


async def warm_vision_model(keep_alive: str = "30m") -> bool:
    """Pre-warm gemma3 for an upcoming vision batch.

    Call BEFORE starting a vision review batch. Blocks until model is loaded.
    Returns False if AMD GPU is busy with ComfyUI-ROCm work.
    """
    await refresh_state()

    if _state.vision_model_warm:
        logger.info(f"{VISION_MODEL} already warm")
        return True

    if _state.comfyui_rocm_busy:
        logger.warning(
            f"Cannot warm {VISION_MODEL} — ComfyUI-ROCm is busy. "
            f"Vision QC deferred."
        )
        return False

    logger.info(f"Warming {VISION_MODEL} (keep_alive={keep_alive})...")
    success = await asyncio.to_thread(_set_keep_alive, VISION_MODEL, keep_alive, 120)

    if success:
        _state.vision_model_warm = True
        logger.info(f"{VISION_MODEL} warm and ready")
    else:
        logger.error(f"Failed to warm {VISION_MODEL}")

    return success


async def release_vision_model() -> bool:
    """Unload gemma3 after vision work is done. Frees ~8GB for ComfyUI-ROCm."""
    if not _state.vision_model_warm:
        return True

    logger.info(f"Unloading {VISION_MODEL} to free VRAM...")
    success = await asyncio.to_thread(_unload_model, VISION_MODEL)

    if success:
        _state.vision_model_warm = False
        logger.info(f"{VISION_MODEL} unloaded, VRAM freed")
    else:
        logger.warning(f"Failed to unload {VISION_MODEL}")

    return success


# ---------------------------------------------------------------------------
# High-level orchestrator helpers — swap VRAM between ComfyUI-ROCm and Ollama
# ---------------------------------------------------------------------------

async def prepare_for_vision(caller: str = "orchestrator",
                             estimated_images: int = 10) -> tuple[bool, str | None]:
    """Prepare AMD GPU for vision QC work (gemma3).

    1. Checks ComfyUI-ROCm isn't actively generating
    2. Frees ComfyUI-ROCm VRAM if it's hogging memory
    3. Claims GPU for vision
    4. Warms gemma3

    Returns (success, claim_id). Caller MUST call finish_vision(claim_id) when done.
    """
    await refresh_state()

    # Don't interrupt active generation
    if _state.comfyui_rocm_busy:
        logger.warning("prepare_for_vision: ComfyUI-ROCm is actively generating, deferring")
        return False, None

    # Claim GPU
    granted, claim_result = await claim_gpu(
        claim_type=ClaimType.VISION_REVIEW,
        caller=caller,
        estimated_duration_s=estimated_images * 10,
    )
    if not granted:
        logger.warning(f"prepare_for_vision: claim denied — {claim_result}")
        return False, None

    claim_id = claim_result

    # Free ComfyUI-ROCm VRAM if AMD is tight
    amd_free = await asyncio.to_thread(_get_amd_free_vram_mb)
    if amd_free is not None and amd_free < VRAM_BUDGET[VISION_MODEL]:
        logger.info(
            f"prepare_for_vision: AMD VRAM low ({amd_free}MB free, need "
            f"{VRAM_BUDGET[VISION_MODEL]}MB). Freeing ComfyUI-ROCm models..."
        )
        await asyncio.to_thread(_free_comfyui_rocm_vram)
        await asyncio.sleep(3)  # Give VRAM time to release

    # Warm gemma3
    success = await warm_vision_model(keep_alive="30m")
    if not success:
        await release_gpu(claim_id)
        logger.error("prepare_for_vision: failed to warm vision model after freeing VRAM")
        return False, None

    logger.info(f"prepare_for_vision: AMD GPU ready for vision QC ({estimated_images} images)")
    return True, claim_id


async def finish_vision(claim_id: str | None):
    """Release AMD GPU after vision QC work. Unloads gemma3."""
    try:
        await release_vision_model()
    except Exception as e:
        logger.warning(f"finish_vision: failed to unload vision model: {e}")
    if claim_id:
        await release_gpu(claim_id)
    logger.info("finish_vision: AMD GPU released for other work")


async def prepare_for_video_gen(caller: str = "orchestrator") -> tuple[bool, str | None]:
    """Prepare AMD GPU for ComfyUI-ROCm video generation.

    1. Unloads ALL Ollama models except nomic-embed-text (frees all GPU VRAM)
    2. Claims GPU for ROCm work

    Returns (success, claim_id). Caller MUST call finish_video_gen(claim_id) when done.
    """
    await refresh_state()

    # Claim GPU
    granted, claim_result = await claim_gpu(
        claim_type=ClaimType.COMFYUI_ROCM,
        caller=caller,
        estimated_duration_s=600,
    )
    if not granted:
        logger.warning(f"prepare_for_video_gen: claim denied — {claim_result}")
        return False, None

    claim_id = claim_result

    # Unload ALL Ollama models except the embedding model
    # This is critical: even "light" models like mistral:7b consume 5-10GB GPU VRAM
    # when Ollama loads them to the AMD GPU, starving ComfyUI-ROCm
    models = await asyncio.to_thread(_get_loaded_models)
    for m in models:
        name = m.get("name", "")
        vram_mb = m.get("size_vram", 0) // (1024 * 1024)
        if EMBED_MODEL not in name and vram_mb > 100:
            logger.info(f"prepare_for_video_gen: unloading {name} ({vram_mb}MB VRAM) for ComfyUI-ROCm")
            await asyncio.to_thread(_unload_model, name)
            await asyncio.sleep(1)

    # Also unload vision model state tracking
    if _state.vision_model_warm:
        _state.vision_model_warm = False

    # Verify VRAM is actually free
    amd_free = await asyncio.to_thread(_get_amd_free_vram_mb)
    if amd_free is not None:
        logger.info(f"prepare_for_video_gen: AMD VRAM {amd_free}MB free after cleanup")
        if amd_free < 8000:
            logger.warning(
                f"prepare_for_video_gen: AMD VRAM still low ({amd_free}MB). "
                f"ComfyUI-ROCm may struggle with large models."
            )

    logger.info("prepare_for_video_gen: AMD GPU ready for video generation")
    return True, claim_id


async def finish_video_gen(claim_id: str | None):
    """Release AMD GPU after video generation."""
    if claim_id:
        await release_gpu(claim_id)
    logger.info("finish_video_gen: AMD GPU released")


# ---------------------------------------------------------------------------
# Claim system — advisory locking for AMD GPU work
# ---------------------------------------------------------------------------

async def claim_gpu(claim_type: ClaimType, caller: str,
                    estimated_duration_s: int = 300,
                    model_needed: str | None = None) -> tuple[bool, str]:
    """Request exclusive-ish access to the AMD GPU for a heavy task.

    Returns (granted, reason). Advisory — callers should respect but can override.
    """
    async with _claim_lock:
        await refresh_state()

        # Check for conflicts
        for claim_id, existing in _state.active_claims.items():
            # Same type can't double-claim
            if existing.claim_type == claim_type:
                return False, f"Already claimed by {existing.caller} since {existing.claimed_at}"

            # Vision vs ComfyUI-ROCm conflict
            if (claim_type == ClaimType.VISION_REVIEW and
                    existing.claim_type == ClaimType.COMFYUI_ROCM):
                return False, "ComfyUI-ROCm has the GPU — vision QC deferred"

            if (claim_type == ClaimType.COMFYUI_ROCM and
                    existing.claim_type == ClaimType.VISION_REVIEW):
                return False, "Vision review has the GPU — ROCm generation deferred"

        # Check actual GPU state
        if claim_type == ClaimType.VISION_REVIEW and _state.comfyui_rocm_busy:
            return False, "ComfyUI-ROCm is actively generating"

        if claim_type == ClaimType.COMFYUI_ROCM and _state.vision_model_warm:
            # Need to unload vision model first
            logger.info("ROCm claim: unloading vision model to free VRAM...")
            await release_vision_model()

        claim = GpuClaim(
            claim_type=claim_type,
            claimed_at=datetime.now(),
            estimated_duration_s=estimated_duration_s,
            caller=caller,
            model_needed=model_needed,
        )
        claim_id = f"{claim_type.value}_{int(time.time())}"
        _state.active_claims[claim_id] = claim

        logger.info(f"GPU claimed: {claim_type.value} by {caller} (~{estimated_duration_s}s)")
        return True, claim_id


async def release_gpu(claim_id: str) -> bool:
    """Release a GPU claim."""
    async with _claim_lock:
        if claim_id in _state.active_claims:
            claim = _state.active_claims.pop(claim_id)
            logger.info(f"GPU released: {claim.claim_type.value} by {claim.caller}")
            return True
        return False


async def cleanup_stale_claims(max_age_s: int = 1800):
    """Remove claims older than max_age_s. Run periodically."""
    async with _claim_lock:
        now = datetime.now()
        stale = [
            cid for cid, c in _state.active_claims.items()
            if (now - c.claimed_at).total_seconds() > max_age_s
        ]
        for cid in stale:
            claim = _state.active_claims.pop(cid)
            logger.warning(
                f"Cleaned stale GPU claim: {claim.claim_type.value} by {claim.caller} "
                f"(aged {(now - claim.claimed_at).total_seconds():.0f}s)"
            )


# ---------------------------------------------------------------------------
# AMD GPU availability check — for orchestrator gates
# ---------------------------------------------------------------------------

async def is_amd_available_for(task: ClaimType) -> tuple[bool, str]:
    """Check if the AMD GPU can accept work of the given type right now.

    Used by orchestrator gates to decide whether to dispatch work.
    """
    await refresh_state()

    # Check existing claims
    for claim in _state.active_claims.values():
        if task == ClaimType.VISION_REVIEW and claim.claim_type == ClaimType.COMFYUI_ROCM:
            return False, f"AMD busy: ComfyUI-ROCm generation ({claim.caller})"
        if task == ClaimType.COMFYUI_ROCM and claim.claim_type == ClaimType.VISION_REVIEW:
            return False, f"AMD busy: vision review ({claim.caller})"

    # Check actual state
    if task == ClaimType.VISION_REVIEW:
        if _state.comfyui_rocm_busy:
            return False, "ComfyUI-ROCm is actively generating"
        return True, "AMD available for vision review"

    if task == ClaimType.COMFYUI_ROCM:
        if _state.vision_model_warm:
            return True, "AMD available (vision model will be unloaded)"
        return True, "AMD available for ROCm generation"

    return True, "AMD available"


# ---------------------------------------------------------------------------
# Status endpoint data
# ---------------------------------------------------------------------------

def get_arbiter_status() -> dict:
    """Full arbiter status for API/dashboard."""
    amd_free = _get_amd_free_vram_mb()
    return {
        "amd_vram_free_mb": amd_free,
        "initialized": _state.initialized,
        "embed_model": {
            "name": EMBED_MODEL,
            "pinned": _state.embed_pinned,
            "loaded": any(EMBED_MODEL in m for m in _state.loaded_models),
            "vram_mb": VRAM_BUDGET[EMBED_MODEL],
        },
        "vision_model": {
            "name": VISION_MODEL,
            "warm": _state.vision_model_warm,
            "loaded": any(VISION_MODEL in m for m in _state.loaded_models),
            "vram_mb": VRAM_BUDGET[VISION_MODEL],
        },
        "comfyui_rocm": {
            "busy": _state.comfyui_rocm_busy,
            "url": COMFYUI_VIDEO_URL,
        },
        "ollama": {
            "loaded_models": _state.loaded_models,
            "total_vram_mb": _state.ollama_vram_mb,
        },
        "claims": {
            cid: {
                "type": c.claim_type.value,
                "caller": c.caller,
                "claimed_at": c.claimed_at.isoformat(),
                "estimated_duration_s": c.estimated_duration_s,
            }
            for cid, c in _state.active_claims.items()
        },
        "vram_budget": VRAM_BUDGET,
    }
