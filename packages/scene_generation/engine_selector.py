"""Video engine selection — benchmarked 2026-03-20.

GPU routing:
  AMD 9070 XT (:8189) — all I2V video generation
    - dasiwa: fastest (198s), 4 steps, baked distillation
    - wan22_14b + lightx2v: 479s, 4 steps
    - wan22_14b standard: 960s, 20 steps (quality mode)
  NVIDIA 3060 (:8188) — keyframes + T2V only
    - wan21 T2V: 84s at 320x480 (establishing shots, no source image)
    - framepack: 420s at 544x704/1s (fallback I2V, very slow)

Default: dasiwa for I2V (has source image), wan21 T2V for T2V (no source image).
Manual engine override via shot.video_engine → respected if set.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

LORA_DIR = Path("/opt/ComfyUI/models/loras")
VALID_ENGINES = {"wan22_14b", "framepack", "framepack_f1", "ltx", "wan", "wan22", "reference_v2v", "dasiwa"}

# Motion keyword → preset mapping
_MOTION_KEYWORDS = {
    "walk": "walking", "walking": "walking", "stroll": "walking",
    "run": "running", "running": "running", "sprint": "running", "dash": "running",
    "fight": "fight_scene", "punch": "fight_scene", "kick": "fight_scene",
    "dodge": "fight_scene", "combat": "fight_scene",
}


@dataclass
class EngineSelection:
    engine: str
    reason: str
    lora_name: str | None = None
    lora_strength: float = 0.8
    motion_preset: str | None = None
    motion_loras: list = field(default_factory=list)


def detect_motion_preset(motion_prompt: str, shot_type: str = "") -> str | None:
    """Detect motion preset from prompt keywords or shot type."""
    if motion_prompt:
        lower = motion_prompt.lower()
        for keyword, preset in _MOTION_KEYWORDS.items():
            if keyword in lower:
                return preset
    if shot_type == "establishing":
        return "establishing"
    return None


def select_engine(
    shot_type: str = "",
    characters_present: list[str] | None = None,
    has_source_image: bool = False,
    blacklisted_engines: list[str] | None = None,
    has_source_video: bool = False,
    project_wan_lora: str | None = None,
    motion_prompt: str | None = None,
) -> EngineSelection:
    """Pick video engine based on benchmarked results.

    Routing:
      - I2V (has source image) → dasiwa on AMD (fastest at 198s)
      - T2V (no source image) → wan21 on NVIDIA (84s, 320x480)
      - Fallback I2V → wan22_14b on AMD
      - Last resort I2V → framepack on NVIDIA (very slow)

    LoRA selection is NOT handled here — it's on the shot record
    (lora_name column) and resolved by builder/regenerate_shot.
    """
    blocked = set(blacklisted_engines or [])
    preset = detect_motion_preset(motion_prompt or "", shot_type)

    # I2V mode (has source image)
    if has_source_image:
        # Best: DaSiWa on AMD (198s, 4 steps, baked distillation)
        if "dasiwa" not in blocked:
            return EngineSelection(
                engine="dasiwa",
                reason="dasiwa I2V on AMD (fastest, 198s)",
                motion_preset=preset,
            )

        # Fallback: Wan22 14B on AMD (479s with lightx2v)
        if "wan22_14b" not in blocked:
            return EngineSelection(
                engine="wan22_14b",
                reason="wan22_14b I2V on AMD (dasiwa blocked)",
                motion_preset=preset,
            )

        # Last resort: FramePack on NVIDIA (420s for 1s, very slow)
        if "framepack" not in blocked:
            return EngineSelection(
                engine="framepack",
                reason="framepack I2V on NVIDIA (all AMD engines blocked)",
                motion_preset=preset,
            )

    # T2V mode (no source image — establishing/environment shots)
    else:
        # Wan 2.1 T2V on NVIDIA (84s, 320x480)
        if "wan" not in blocked:
            return EngineSelection(
                engine="wan",
                reason="wan21 T2V on NVIDIA (320x480, 49f)",
                motion_preset=preset,
            )

    # Nothing available
    return EngineSelection(
        engine="dasiwa",
        reason="dasiwa (all alternatives blocked, forcing default)",
        motion_preset=preset,
    )
