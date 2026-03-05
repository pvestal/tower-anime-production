"""Variety Check — CLIP-based similarity enforcement between consecutive shots.

After generation completes, compares the output against recent accepted shots
in the same scene. If similarity exceeds threshold, flags the shot as "too_similar"
with a suggestion for what to change.

Uses open_clip ViT-B-32 for 512-dim embeddings. Runs on AMD GPU (same as Ollama).
"""

import logging
from pathlib import Path
from typing import Any

import asyncpg
import numpy as np

logger = logging.getLogger(__name__)

# Lazy-loaded CLIP model singleton
_clip_model = None
_clip_preprocess = None
_clip_tokenizer = None

# Similarity threshold: shots above this are flagged as "too similar"
SIMILARITY_THRESHOLD = 0.85


def _load_clip():
    """Lazy-load CLIP model. ~400MB VRAM on first call."""
    global _clip_model, _clip_preprocess, _clip_tokenizer
    if _clip_model is not None:
        return

    import open_clip
    import torch

    device = "cpu"  # Safe default; AMD GPU via ROCm if available
    try:
        if torch.cuda.is_available():
            device = "cuda"
    except Exception:
        pass

    _clip_model, _, _clip_preprocess = open_clip.create_model_and_transforms(
        "ViT-B-32", pretrained="laion2b_s34b_b79k", device=device,
    )
    _clip_tokenizer = open_clip.get_tokenizer("ViT-B-32")
    _clip_model.eval()
    logger.info(f"variety_check: CLIP ViT-B-32 loaded on {device}")


def embed_image(image_path: str | Path) -> np.ndarray | None:
    """Compute CLIP embedding for an image. Returns 512-dim vector or None on failure."""
    try:
        _load_clip()
        import torch
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        img_tensor = _clip_preprocess(img).unsqueeze(0)

        device = next(_clip_model.parameters()).device
        img_tensor = img_tensor.to(device)

        with torch.no_grad():
            embedding = _clip_model.encode_image(img_tensor)
            embedding = embedding / embedding.norm(dim=-1, keepdim=True)

        return embedding.cpu().numpy().flatten()
    except Exception as e:
        logger.warning(f"variety_check: failed to embed image {image_path}: {e}")
        return None


def embed_text(text: str) -> np.ndarray | None:
    """Compute CLIP text embedding. Returns 512-dim vector or None on failure."""
    try:
        _load_clip()
        import torch

        tokens = _clip_tokenizer([text])
        device = next(_clip_model.parameters()).device
        tokens = tokens.to(device)

        with torch.no_grad():
            embedding = _clip_model.encode_text(tokens)
            embedding = embedding / embedding.norm(dim=-1, keepdim=True)

        return embedding.cpu().numpy().flatten()
    except Exception as e:
        logger.warning(f"variety_check: failed to embed text: {e}")
        return None


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


async def check_sequence_variety(
    conn: asyncpg.Connection,
    shot_id,
    scene_id,
    output_image_path: str | None = None,
) -> dict[str, Any]:
    """Check if a newly generated shot is too similar to recent shots in the same scene.

    Args:
        conn: DB connection
        shot_id: UUID of the shot being checked
        scene_id: UUID of the scene
        output_image_path: Path to the last frame or output image to compare

    Returns:
        {
            "similar": bool,
            "most_similar_shot_id": str | None,
            "similarity_score": float,
            "suggestion": str | None,
        }
    """
    result = {
        "similar": False,
        "most_similar_shot_id": None,
        "similarity_score": 0.0,
        "suggestion": None,
    }

    if not output_image_path or not Path(output_image_path).exists():
        return result

    # Get recent completed shots in the same scene (excluding current)
    recent_shots = await conn.fetch("""
        SELECT id::text as shot_id, last_frame_path, pose_type,
               camera_angle, must_differ_from
        FROM shots
        WHERE scene_id = $1 AND id != $2 AND status = 'completed'
              AND last_frame_path IS NOT NULL
        ORDER BY shot_number DESC
        LIMIT 5
    """, scene_id, shot_id)

    if not recent_shots:
        return result

    # Embed current shot
    current_embedding = embed_image(output_image_path)
    if current_embedding is None:
        return result

    # Get the must_differ_from list for the current shot
    current_shot = await conn.fetchrow(
        "SELECT must_differ_from FROM shots WHERE id = $1", shot_id
    )
    must_differ = set()
    if current_shot and current_shot["must_differ_from"]:
        must_differ = {str(uid) for uid in current_shot["must_differ_from"]}

    # Compare against each recent shot
    max_sim = 0.0
    most_similar_id = None
    most_similar_pose = None

    for rs in recent_shots:
        if not rs["last_frame_path"] or not Path(rs["last_frame_path"]).exists():
            continue

        ref_embedding = embed_image(rs["last_frame_path"])
        if ref_embedding is None:
            continue

        sim = cosine_similarity(current_embedding, ref_embedding)
        if sim > max_sim:
            max_sim = sim
            most_similar_id = rs["shot_id"]
            most_similar_pose = rs["pose_type"]

    result["similarity_score"] = round(max_sim, 4)
    result["most_similar_shot_id"] = most_similar_id

    # Flag if similarity exceeds threshold AND the shot is in must_differ_from
    if max_sim > SIMILARITY_THRESHOLD:
        if most_similar_id and (most_similar_id in must_differ or not must_differ):
            result["similar"] = True
            suggestions = []
            if most_similar_pose:
                suggestions.append(f"avoid pose '{most_similar_pose}'")
            suggestions.append("try different camera angle")
            suggestions.append("add specific body language to negative prompt")
            result["suggestion"] = "; ".join(suggestions)

    return result
