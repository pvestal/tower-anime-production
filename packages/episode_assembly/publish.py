"""Jellyfin publishing — create series directory structure and trigger library scan."""

import logging
import os
import re
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

JELLYFIN_URL = "http://localhost:8096"
JELLYFIN_API_KEY = os.getenv("JELLYFIN_API_KEY", "")
MEDIA_ROOT = Path("/mnt/1TB-storage/media/anime")


def sanitize_filename(name: str) -> str:
    """Remove characters that are problematic in filenames."""
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()


async def publish_episode(
    project_name: str,
    episode_number: int,
    episode_title: str,
    video_path: str,
    season: int = 1,
    thumbnail_path: str | None = None,
) -> dict:
    """Publish an episode to Jellyfin-compatible directory structure.

    Creates:
        /mnt/1TB-storage/media/anime/{Project Name}/Season 01/S01E01 - {Title}.mp4

    Returns dict with published paths.
    """
    safe_project = sanitize_filename(project_name)
    season_dir = MEDIA_ROOT / safe_project / f"Season {season:02d}"
    season_dir.mkdir(parents=True, exist_ok=True)

    episode_filename = f"S{season:02d}E{episode_number:02d} - {sanitize_filename(episode_title)}.mp4"
    dest_path = season_dir / episode_filename

    # Symlink to avoid duplicating storage
    if dest_path.exists() or dest_path.is_symlink():
        dest_path.unlink()
    os.symlink(video_path, str(dest_path))
    logger.info(f"Published: {dest_path} -> {video_path}")

    result = {
        "published_path": str(dest_path),
        "series_dir": str(season_dir.parent),
        "season_dir": str(season_dir),
        "filename": episode_filename,
    }

    # Copy thumbnail if provided
    if thumbnail_path and Path(thumbnail_path).exists():
        thumb_dest = season_dir / f"S{season:02d}E{episode_number:02d} - {sanitize_filename(episode_title)}-thumb.jpg"
        import shutil
        shutil.copy2(thumbnail_path, str(thumb_dest))
        result["thumbnail_path"] = str(thumb_dest)

    # Trigger Jellyfin library scan
    scan_result = await trigger_jellyfin_scan()
    result["jellyfin_scan"] = scan_result

    return result


async def trigger_jellyfin_scan() -> str:
    """Trigger Jellyfin library refresh via API."""
    if not JELLYFIN_API_KEY:
        return "skipped (no JELLYFIN_API_KEY configured)"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{JELLYFIN_URL}/Library/Refresh",
                headers={"X-Emby-Token": JELLYFIN_API_KEY},
            )
            if resp.status_code < 300:
                logger.info("Jellyfin library scan triggered")
                return "triggered"
            else:
                logger.warning(f"Jellyfin scan returned {resp.status_code}")
                return f"failed ({resp.status_code})"
    except Exception as e:
        logger.warning(f"Jellyfin scan failed: {e}")
        return f"error ({e})"
