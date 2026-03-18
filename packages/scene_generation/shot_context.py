"""Shot context resolution helpers — deduplicated from builder.py and scene_crud.py.

Contains pure utility functions for:
- Scene-deterministic seed derivation
- Video dimension resolution (engine defaults + landscape swap)
- Color style resolution (from checkpoint style anchor)
- Checkpoint model lookup from project generation style
"""

import hashlib
import logging

from .video_config import get_engine_defaults

logger = logging.getLogger(__name__)


def derive_scene_seed(scene_id: str, shot_number: int) -> int:
    """Derive a deterministic per-shot seed from a scene UUID and shot number.

    Uses SHA-256 of the scene_id string to produce a stable base seed,
    then offsets by shot_number for per-shot variation within the scene.

    Args:
        scene_id: Scene UUID as string.
        shot_number: Shot number (1-based) within the scene.

    Returns:
        Deterministic integer seed in range [0, 2**63).
    """
    seed_bytes = hashlib.sha256(str(scene_id).encode()).digest()
    base_seed = int.from_bytes(seed_bytes[:8], "big") % (2**63)
    return base_seed + (shot_number or 0)


def resolve_video_dimensions(
    engine: str,
    project_width: int | None,
    project_height: int | None,
) -> tuple[int, int]:
    """Resolve video output dimensions for a given engine.

    Reads engine defaults from video_models.yaml, then swaps width/height
    if the project's aspect ratio is landscape (width > height).

    Special cases:
    - wan engine uses fixed 480x720 default (portrait) / 720x480 (landscape)
    - wan22 uses engine defaults from config
    - wan22_14b uses engine defaults from config
    - ltx_long uses fixed 320x512 (portrait) / 512x320 (landscape)

    Args:
        engine: Video engine name (wan, wan22, wan22_14b, dasiwa, ltx_long, etc.)
        project_width: Project-level width from generation_styles, or None.
        project_height: Project-level height from generation_styles, or None.

    Returns:
        Tuple of (width, height) for the video generation.
    """
    is_landscape = (
        project_width is not None
        and project_height is not None
        and project_width > project_height
    )

    if engine == "wan":
        # Wan T2V: fixed 480x720 portrait, 720x480 landscape
        if is_landscape:
            return 720, 480
        return 480, 720

    if engine == "ltx_long":
        if is_landscape:
            return 512, 320
        return 320, 512

    # For wan22, wan22_14b, dasiwa — read from engine defaults config
    cfg_key = engine
    if engine == "dasiwa":
        cfg_key = "wan22_14b_dasiwa"
    eng_cfg = get_engine_defaults(cfg_key)
    w = eng_cfg.get("width", 480)
    h = eng_cfg.get("height", 720)

    if is_landscape:
        # Swap for landscape
        if engine == "wan22":
            return 768, 512
        return h, w

    return w, h


def resolve_color_style(style_anchor: str) -> str:
    """Resolve the color grading style from a style_anchor string.

    Used by video post-processing to select the right color grade LUT.

    Args:
        style_anchor: Style anchor string from the project checkpoint
                      (e.g. "anime style, cinematic" or "photorealistic, live action").

    Returns:
        One of "anthro", "photorealistic", or "anime".
    """
    if style_anchor and "anthro" in style_anchor:
        return "anthro"
    elif style_anchor and "photorealistic" in style_anchor:
        return "photorealistic"
    return "anime"


async def resolve_checkpoint(conn, project_id: int) -> str:
    """Look up the project's checkpoint model from generation_styles.

    Queries the project's default_style → generation_styles join to find
    the checkpoint model filename. Falls back to waiIllustriousSDXL_v160.

    Args:
        conn: asyncpg connection.
        project_id: Project ID to look up.

    Returns:
        Checkpoint filename with .safetensors extension.
    """
    default_ckpt = "waiIllustriousSDXL_v160.safetensors"
    try:
        row = await conn.fetchrow(
            "SELECT gs.checkpoint_model FROM projects p "
            "JOIN generation_styles gs ON p.default_style = gs.style_name "
            "WHERE p.id = $1",
            project_id,
        )
        if row and row["checkpoint_model"]:
            ckpt = row["checkpoint_model"]
            if not ckpt.endswith(".safetensors"):
                ckpt += ".safetensors"
            return ckpt
    except Exception:
        pass
    return default_ckpt
