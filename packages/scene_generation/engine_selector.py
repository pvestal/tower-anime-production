"""Video engine selection — simplified.

Default: wan22_14b for everything.
- Has source image → I2V mode
- No source image → T2V mode
- Content LoRA on shot → applied automatically by builder
- Manual engine override via shot.video_engine → respected if set
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

LORA_DIR = Path("/opt/ComfyUI/models/loras")
VALID_ENGINES = {"wan22_14b", "framepack", "framepack_f1", "ltx", "wan", "wan22", "reference_v2v"}


@dataclass
class EngineSelection:
    engine: str
    reason: str
    lora_name: str | None = None
    lora_strength: float = 0.8
    motion_preset: str | None = None
    motion_loras: list = field(default_factory=list)


def select_engine(
    shot_type: str = "",
    characters_present: list[str] | None = None,
    has_source_image: bool = False,
    blacklisted_engines: list[str] | None = None,
    has_source_video: bool = False,
    project_wan_lora: str | None = None,
    motion_prompt: str | None = None,
) -> EngineSelection:
    """Pick video engine. Simple: wan22_14b for everything.

    LoRA selection is NOT handled here — it's on the shot record
    (lora_name column) and resolved by builder/regenerate_shot.
    """
    blocked = set(blacklisted_engines or [])

    # Default: wan22_14b
    if "wan22_14b" not in blocked:
        mode = "I2V" if has_source_image else "T2V"
        return EngineSelection(
            engine="wan22_14b",
            reason=f"wan22_14b {mode}",
        )

    # Fallback if wan22_14b is blacklisted for this shot
    if "framepack" not in blocked and has_source_image:
        return EngineSelection(
            engine="framepack",
            reason="framepack I2V (wan22_14b blacklisted)",
        )

    # Last resort
    return EngineSelection(
        engine="wan22_14b",
        reason="wan22_14b (all alternatives blocked)",
    )
