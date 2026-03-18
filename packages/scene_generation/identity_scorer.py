"""Face-embedding identity scorer for video QC.

Uses InsightFace buffalo_l (ArcFace w600k_r50) via ONNX Runtime on CPU.
Compares video frames against character reference embeddings to produce an
identity_score (0-1 cosine similarity).

~50ms per frame on CPU, ~300ms for a 5-frame video sample.
"""

import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_INSIGHTFACE_ROOT = "/opt/ComfyUI/models/insightface"

# Lazy-loaded FaceAnalysis app
_app = None

# Cached reference embeddings: character_slug → np.ndarray (512,)
_ref_cache: dict[str, np.ndarray] = {}


def _get_app():
    """Lazy-load InsightFace app (CPU only, ~200ms first call)."""
    global _app
    if _app is None:
        from insightface.app import FaceAnalysis
        _app = FaceAnalysis(
            name="buffalo_l",
            root=_INSIGHTFACE_ROOT,
            providers=["CPUExecutionProvider"],
        )
        _app.prepare(ctx_id=-1, det_size=(320, 320))
        logger.info("InsightFace loaded (buffalo_l, CPU, det_size=320)")
    return _app


def get_face_embedding(image_path: str) -> Optional[np.ndarray]:
    """Extract face embedding from an image file. Returns None if no face found."""
    img = cv2.imread(str(image_path))
    if img is None:
        logger.warning(f"Could not read image: {image_path}")
        return None
    return _embedding_from_bgr(img)


def _embedding_from_bgr(img: np.ndarray) -> Optional[np.ndarray]:
    """Extract normalized 512-dim embedding from a BGR image."""
    app = _get_app()
    faces = app.get(img)
    if not faces:
        return None
    # Use largest face (by bbox area)
    face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    emb = face.embedding.astype(np.float32)
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb


def build_reference_embedding(
    character_slug: str,
    image_paths: list[str],
    max_images: int = 10,
) -> Optional[np.ndarray]:
    """Build a reference embedding by averaging faces from multiple images. Cached."""
    if character_slug in _ref_cache:
        return _ref_cache[character_slug]

    embeddings = []
    for path in image_paths[:max_images]:
        emb = get_face_embedding(path)
        if emb is not None:
            embeddings.append(emb)

    if not embeddings:
        logger.warning(f"No faces found in reference images for {character_slug}")
        return None

    ref = np.mean(embeddings, axis=0).astype(np.float32)
    ref = ref / np.linalg.norm(ref)
    _ref_cache[character_slug] = ref
    logger.info(f"Built reference embedding for '{character_slug}' from {len(embeddings)}/{len(image_paths)} images")
    return ref


def score_video_identity(
    video_path: str,
    reference_embedding: np.ndarray,
    sample_count: int = 5,
) -> dict:
    """Score a video's identity preservation against a reference embedding.

    Samples evenly-spaced frames (skipping first/last 10%), extracts face
    embeddings, computes cosine similarity against reference.

    Returns:
        identity_score: float (0-1, mean cosine similarity across detected faces)
        frame_scores: list[float]
        faces_found: int
        frames_sampled: int
        min_score: float (worst frame)
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.warning(f"Could not open video: {video_path}")
        return _empty_result()

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames < 2:
        cap.release()
        return _empty_result()

    start = max(1, int(total_frames * 0.1))
    end = max(start + 1, int(total_frames * 0.9))
    indices = np.linspace(start, end, sample_count, dtype=int)

    frame_scores = []
    faces_found = 0

    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if not ret:
            continue

        emb = _embedding_from_bgr(frame)
        if emb is None:
            continue

        sim = float(np.dot(emb, reference_embedding))
        frame_scores.append(sim)
        faces_found += 1

    cap.release()

    if not frame_scores:
        return _empty_result(frames_sampled=len(indices))

    return {
        "identity_score": float(np.clip(np.mean(frame_scores), 0, 1)),
        "frame_scores": frame_scores,
        "faces_found": faces_found,
        "frames_sampled": len(indices),
        "min_score": float(min(frame_scores)),
    }


def score_image_identity(
    image_path: str,
    reference_embedding: np.ndarray,
) -> float:
    """Score a single image's identity match. Returns cosine similarity (0-1)."""
    emb = get_face_embedding(image_path)
    if emb is None:
        return 0.0
    return float(np.clip(np.dot(emb, reference_embedding), 0, 1))


def clear_cache():
    """Clear the reference embedding cache."""
    _ref_cache.clear()


def _empty_result(frames_sampled: int = 0) -> dict:
    return {
        "identity_score": 0.0,
        "frame_scores": [],
        "faces_found": 0,
        "frames_sampled": frames_sampled,
        "min_score": 0.0,
    }
