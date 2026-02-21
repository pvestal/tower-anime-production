"""Perceptual hash deduplication for ingestion paths.

Uses the average-hash implementation from packages.visual_pipeline.vision to detect
near-duplicate images before they enter a character's dataset.
"""

import logging
from pathlib import Path

from packages.core.config import BASE_PATH
from packages.visual_pipeline.vision import perceptual_hash

logger = logging.getLogger(__name__)

# In-memory hash caches: slug -> set of hex hash strings.
# Populated lazily on first check per character.
_hash_caches: dict[str, set[str]] = {}


def build_hash_index(slug: str) -> set[str]:
    """Build (or return cached) perceptual hash index for a character's existing dataset."""
    if slug in _hash_caches:
        return _hash_caches[slug]

    hashes: set[str] = set()
    images_dir = BASE_PATH / slug / "images"
    if images_dir.is_dir():
        for img in images_dir.glob("*.png"):
            try:
                h = perceptual_hash(img)
                hashes.add(h)
            except Exception:
                pass
    _hash_caches[slug] = hashes
    logger.debug(f"Built hash index for {slug}: {len(hashes)} images")
    return hashes


def is_duplicate(image_path: Path, slug: str) -> bool:
    """Check whether image_path is a perceptual duplicate of anything in slug's dataset."""
    index = build_hash_index(slug)
    try:
        h = perceptual_hash(image_path)
    except Exception:
        return False
    return h in index


def register_hash(image_path: Path, slug: str) -> None:
    """Add image_path's hash to the in-memory cache after a successful copy."""
    index = build_hash_index(slug)
    try:
        h = perceptual_hash(image_path)
        index.add(h)
    except Exception:
        pass


def invalidate_cache(slug: str | None = None) -> None:
    """Drop cached hashes. If slug is None, drop all."""
    if slug is None:
        _hash_caches.clear()
    else:
        _hash_caches.pop(slug, None)
