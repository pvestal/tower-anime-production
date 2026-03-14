#!/usr/bin/env python3
"""
Motion LoRA Training Clip Collector
====================================
Downloads CC0 stock video clips from Pexels and Pixabay for training
SFW motion LoRAs (walk, run, talk, hug) on WAN 2.2 14B I2V.

Usage:
    # Collect clips for all Priority 1 LoRAs
    python3 collect_motion_clips.py --all

    # Collect clips for a specific LoRA
    python3 collect_motion_clips.py --lora walk_cycle

    # Collect with custom clip count target
    python3 collect_motion_clips.py --lora run_cycle --target 25

    # Dry run (search only, don't download)
    python3 collect_motion_clips.py --lora talk_gesture --dry-run

    # List available LoRA definitions
    python3 collect_motion_clips.py --list

API Keys:
    Set environment variables before running:
        export PEXELS_API_KEY="your_key_here"
        export PIXABAY_API_KEY="your_key_here"

    Get free keys at:
        https://www.pexels.com/api/
        https://pixabay.com/api/docs/

Output:
    /opt/anime-studio/datasets/_motion_loras/{lora_name}/
        clips/          - Downloaded MP4 files (trimmed to 3-6s)
        originals/      - Original untrimmed downloads
        captions.json   - Auto-generated captions per clip
        manifest.json   - Dataset manifest for training
"""

import argparse
import json
import logging
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import requests
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("motion-clips")

# ---------------------------------------------------------------------------
# Search query definitions per LoRA
# Each LoRA has multiple search queries to get diverse footage
# ---------------------------------------------------------------------------
LORA_SEARCH_QUERIES = {
    "walk_cycle": {
        "label": "Walking",
        "priority": 1,
        "target_clips": 25,
        "clip_length": (3, 6),
        "min_resolution": 720,
        "queries": [
            "person walking forward sidewalk",
            "woman walking hallway",
            "man walking street full body",
            "walking green screen",
            "person walking side view",
            "walking away camera full body",
            "pedestrian walking urban",
            "model walking runway catwalk",
            "person strolling park path",
            "walking treadmill side view",
        ],
        "pixabay_queries": [
            "person walking",
            "walking sidewalk",
            "pedestrian street",
            "walking hallway",
            "strolling park",
        ],
        "caption_template": "full body {gender} walking {direction} on a {surface}, neutral expression",
        "caption_vars": {
            "gender": ["person", "woman", "man"],
            "direction": ["forward", "from left to right", "away from camera", "toward camera"],
            "surface": ["sidewalk", "hallway", "path", "street", "flat ground"],
        },
        "avoid_keywords": ["crowd", "group", "dance", "run", "jog"],
    },
    "run_cycle": {
        "label": "Running / Jogging",
        "priority": 1,
        "target_clips": 20,
        "clip_length": (3, 6),
        "min_resolution": 720,
        "queries": [
            "person jogging track",
            "woman running park path",
            "man running sidewalk full body",
            "jogging treadmill side view",
            "running athlete track",
            "person sprinting street",
            "jogger running morning",
            "running exercise outdoor",
        ],
        "pixabay_queries": [
            "person running",
            "jogging track",
            "runner exercise",
            "sprinting athlete",
        ],
        "caption_template": "{gender} {speed} on a {surface}",
        "caption_vars": {
            "gender": ["person", "woman", "man"],
            "speed": ["jogging steadily", "running", "sprinting", "jogging at moderate pace"],
            "surface": ["track", "park path", "sidewalk", "treadmill", "street"],
        },
        "avoid_keywords": ["marathon", "crowd", "group", "race start"],
    },
    "talk_gesture": {
        "label": "Talking / Hand Gestures",
        "priority": 1,
        "target_clips": 25,
        "clip_length": (3, 6),
        "min_resolution": 720,
        "queries": [
            "person talking hand gestures",
            "woman speaking gesturing hands",
            "man talking to camera upper body",
            "person presenting hand movements",
            "interview talking gestures",
            "speaker gesturing presentation",
            "person explaining with hands",
            "conversation gestures medium shot",
            "podcast host talking",
            "person talking expressively",
        ],
        "pixabay_queries": [
            "person talking gestures",
            "speaking presentation",
            "interview talking",
            "person explaining",
            "conversation hands",
        ],
        "caption_template": "{gender} talking while {gesture}, {setting}",
        "caption_vars": {
            "gender": ["person", "woman", "man"],
            "gesture": [
                "gesturing with hands",
                "making expressive hand movements",
                "nodding and gesturing",
                "pointing and explaining",
            ],
            "setting": [
                "indoor studio",
                "office setting",
                "outdoor cafe",
                "living room",
                "neutral background",
            ],
        },
        "avoid_keywords": ["crowd", "audience", "concert", "singing"],
    },
    "hug_interaction": {
        "label": "Hug (SFW)",
        "priority": 1,
        "target_clips": 25,
        "clip_length": (3, 6),
        "min_resolution": 720,
        "queries": [
            "two people hugging",
            "friends hugging goodbye",
            "couple embracing warmly",
            "family reunion hug",
            "hugging greeting",
            "warm embrace two people",
            "people hugging outdoors",
            "hug farewell airport",
            "friends reuniting hug",
            "gentle embrace couple",
        ],
        "pixabay_queries": [
            "people hugging",
            "couple embrace",
            "friends hug",
            "reunion hug",
            "warm embrace",
        ],
        "caption_template": "two people hugging {style}, {setting}",
        "caption_vars": {
            "style": ["warmly", "gently", "tightly", "with arms wrapped around each other"],
            "setting": [
                "standing in a park",
                "indoor setting",
                "at a doorway",
                "on a street",
                "in an open area",
            ],
        },
        "avoid_keywords": ["kiss", "romantic bed", "explicit", "chest focused"],
    },
    # --- Priority 2 ---
    "jump_action": {
        "label": "Jump / Hop",
        "priority": 2,
        "target_clips": 15,
        "clip_length": (2, 5),
        "min_resolution": 720,
        "queries": [
            "person jumping in place",
            "jump rope workout",
            "vertical jump fitness",
            "person leaping forward",
            "jumping exercise gym",
            "hop jump full body",
        ],
        "pixabay_queries": [
            "person jumping",
            "jump exercise",
            "leaping fitness",
        ],
        "caption_template": "{gender} jumping {style}, feet leaving ground",
        "caption_vars": {
            "gender": ["person", "woman", "man"],
            "style": ["in place", "forward", "with both feet", "energetically"],
        },
        "avoid_keywords": ["parkour", "acrobatics", "trampoline", "flip"],
    },
    "kiss_sfw": {
        "label": "Kiss (PG)",
        "priority": 2,
        "target_clips": 20,
        "clip_length": (2, 5),
        "min_resolution": 720,
        "queries": [
            "couple quick kiss",
            "peck on cheek",
            "gentle kiss couple",
            "wedding kiss brief",
            "light kiss greeting",
            "sweet kiss couple outdoor",
        ],
        "pixabay_queries": [
            "couple kiss gentle",
            "kiss cheek",
            "sweet kiss",
        ],
        "caption_template": "{gender_pair} sharing a {kiss_type}, {setting}",
        "caption_vars": {
            "gender_pair": ["couple", "two people", "man and woman"],
            "kiss_type": ["gentle kiss", "light peck", "quick kiss", "soft kiss on the cheek"],
            "setting": ["standing outdoors", "at a doorway", "in a garden", "under soft light"],
        },
        "avoid_keywords": ["makeout", "explicit", "tongue", "passionate"],
    },
    "cook_action": {
        "label": "Cooking",
        "priority": 2,
        "target_clips": 25,
        "clip_length": (3, 6),
        "min_resolution": 720,
        "queries": [
            "person cooking kitchen stirring",
            "chef chopping vegetables",
            "cooking pan flipping food",
            "person stirring pot kitchen",
            "cooking preparation cutting",
            "chef cooking close up hands",
            "kitchen cooking overhead view",
            "person cooking stove",
        ],
        "pixabay_queries": [
            "cooking kitchen",
            "chef stirring",
            "chopping vegetables",
            "cooking pan",
        ],
        "caption_template": "person cooking in a kitchen, {action}",
        "caption_vars": {
            "action": [
                "stirring a pot",
                "chopping vegetables on a cutting board",
                "flipping food in a pan",
                "mixing ingredients in a bowl",
                "sauteing in a skillet",
            ],
        },
        "avoid_keywords": ["bbq", "outdoor grill", "party", "eating"],
    },
    "swim_cycle": {
        "label": "Swimming",
        "priority": 3,
        "target_clips": 20,
        "clip_length": (4, 8),
        "min_resolution": 720,
        "queries": [
            "person swimming pool side view",
            "freestyle swimming underwater",
            "swimming breaststroke",
            "swimmer pool lane",
            "underwater swimming clear water",
            "person swimming ocean calm",
        ],
        "pixabay_queries": [
            "swimming pool",
            "swimmer underwater",
            "freestyle swimming",
        ],
        "caption_template": "{gender} swimming {stroke} in a {water_body}, {view}",
        "caption_vars": {
            "gender": ["person", "woman", "man"],
            "stroke": ["freestyle", "breaststroke", "with steady strokes"],
            "water_body": ["pool", "calm ocean", "clear water"],
            "view": ["side view", "underwater camera", "above-water tracking shot"],
        },
        "avoid_keywords": ["surfing", "splash fight", "water park", "diving board"],
    },
}


# ---------------------------------------------------------------------------
# API clients
# ---------------------------------------------------------------------------

class PexelsClient:
    """Pexels Video Search API client."""

    BASE_URL = "https://api.pexels.com/videos/search"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers["Authorization"] = api_key

    def search(self, query: str, per_page: int = 15, page: int = 1,
               min_duration: int = 3, max_duration: int = 10,
               orientation: str = "landscape") -> list[dict]:
        """Search for videos, return normalized results."""
        params = {
            "query": query,
            "per_page": min(per_page, 80),
            "page": page,
            "orientation": orientation,
        }
        try:
            resp = self.session.get(self.BASE_URL, params=params, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning("Pexels search failed for '%s': %s", query, e)
            return []

        results = []
        for video in resp.json().get("videos", []):
            duration = video.get("duration", 0)
            if duration < min_duration or duration > max_duration * 3:
                continue  # Allow longer clips — we'll trim later

            # Pick best quality file (720p+ preferred)
            best_file = None
            for vf in video.get("video_files", []):
                w = vf.get("width", 0)
                h = vf.get("height", 0)
                if min(w, h) >= 720 and vf.get("link"):
                    if best_file is None or (vf.get("width", 0) <= 1920):
                        best_file = vf
            if not best_file:
                # Fallback to any available file
                for vf in video.get("video_files", []):
                    if vf.get("link"):
                        best_file = vf
                        break

            if best_file:
                results.append({
                    "source": "pexels",
                    "id": video["id"],
                    "url": best_file["link"],
                    "width": best_file.get("width", 0),
                    "height": best_file.get("height", 0),
                    "duration": duration,
                    "query": query,
                })
        return results


class PixabayClient:
    """Pixabay Video Search API client."""

    BASE_URL = "https://pixabay.com/api/videos/"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, query: str, per_page: int = 15, page: int = 1,
               min_duration: int = 3) -> list[dict]:
        """Search for videos, return normalized results."""
        params = {
            "key": self.api_key,
            "q": query,
            "per_page": min(per_page, 200),
            "page": page,
            "safesearch": "true",
            "video_type": "all",
        }
        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning("Pixabay search failed for '%s': %s", query, e)
            return []

        results = []
        for hit in resp.json().get("hits", []):
            duration = hit.get("duration", 0)
            if duration < min_duration:
                continue

            # Prefer 'medium' quality (720p typically), fall back to 'small'
            videos = hit.get("videos", {})
            for quality in ("medium", "large", "small"):
                vf = videos.get(quality, {})
                if vf.get("url") and vf.get("width", 0) >= 640:
                    results.append({
                        "source": "pixabay",
                        "id": hit["id"],
                        "url": vf["url"],
                        "width": vf.get("width", 0),
                        "height": vf.get("height", 0),
                        "duration": duration,
                        "query": query,
                    })
                    break
        return results


# ---------------------------------------------------------------------------
# Video processing
# ---------------------------------------------------------------------------

def get_video_info(path: Path) -> Optional[dict]:
    """Get duration and resolution using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams", "-show_format",
                str(path),
            ],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                return {
                    "duration": duration,
                    "width": int(stream.get("width", 0)),
                    "height": int(stream.get("height", 0)),
                    "fps": eval(stream.get("r_frame_rate", "24/1")),
                }
    except Exception as e:
        log.warning("ffprobe failed for %s: %s", path, e)
    return None


def trim_clip(input_path: Path, output_path: Path,
              target_min: float = 3.0, target_max: float = 6.0) -> bool:
    """Trim a video clip to target duration range. Picks a random segment if longer.
    Extracts audio to a separate SFX file for the foley library."""
    info = get_video_info(input_path)
    if not info:
        return False

    duration = info["duration"]
    if duration < target_min:
        log.warning("Clip %s too short (%.1fs < %.1fs), skipping", input_path.name, duration, target_min)
        return False

    if duration <= target_max:
        # Already within range — just copy (re-encode to normalize codec)
        start = 0.0
        length = duration
    else:
        # Pick a random segment within the clip
        length = random.uniform(target_min, target_max)
        max_start = duration - length
        start = random.uniform(0.3, max(0.3, max_start))  # Skip first 0.3s (common fade-in)

    try:
        # Video clip (no audio — LoRA training doesn't need it)
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", f"{start:.2f}",
                "-i", str(input_path),
                "-t", f"{length:.2f}",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-an",
                "-r", "24",  # Normalize to 24fps
                "-vf", "scale='min(1280,iw)':'min(720,ih)':force_original_aspect_ratio=decrease",
                str(output_path),
            ],
            capture_output=True, text=True, timeout=120,
        )

        # Extract audio to SFX library (same trim window)
        sfx_dir = output_path.parent.parent / "sfx"
        sfx_dir.mkdir(exist_ok=True)
        sfx_path = sfx_dir / (output_path.stem + ".wav")
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", f"{start:.2f}",
                "-i", str(input_path),
                "-t", f"{length:.2f}",
                "-vn",  # No video
                "-acodec", "pcm_s16le",
                "-ar", "44100",
                "-ac", "1",  # Mono for SFX
                str(sfx_path),
            ],
            capture_output=True, text=True, timeout=60,
        )
        if sfx_path.exists() and sfx_path.stat().st_size < 1000:
            # Silent or near-empty audio — not useful as SFX
            sfx_path.unlink()
        elif sfx_path.exists():
            log.info("  SFX extracted: %s", sfx_path.name)

        return output_path.exists() and output_path.stat().st_size > 10000
    except Exception as e:
        log.warning("ffmpeg trim failed for %s: %s", input_path.name, e)
        return False


def generate_caption(lora_def: dict, clip_index: int) -> str:
    """Generate a caption from the template with random variable substitution."""
    template = lora_def["caption_template"]
    caption_vars = lora_def.get("caption_vars", {})

    result = template
    for key, values in caption_vars.items():
        placeholder = "{" + key + "}"
        if placeholder in result:
            # Rotate through values based on clip index for diversity
            value = values[clip_index % len(values)]
            result = result.replace(placeholder, value)
    return result


# ---------------------------------------------------------------------------
# Download orchestrator
# ---------------------------------------------------------------------------

def download_file(url: str, dest: Path, timeout: int = 120) -> bool:
    """Download a file with progress indication."""
    try:
        resp = requests.get(url, stream=True, timeout=timeout)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
        if total and downloaded < total * 0.9:
            log.warning("Incomplete download: %s (%d/%d bytes)", dest.name, downloaded, total)
            dest.unlink(missing_ok=True)
            return False
        return True
    except Exception as e:
        log.warning("Download failed for %s: %s", url, e)
        dest.unlink(missing_ok=True)
        return False


def collect_clips_for_lora(
    lora_name: str,
    pexels: Optional[PexelsClient],
    pixabay: Optional[PixabayClient],
    target_override: Optional[int] = None,
    dry_run: bool = False,
) -> dict:
    """Collect, download, and trim clips for a single motion LoRA."""

    lora_def = LORA_SEARCH_QUERIES.get(lora_name)
    if not lora_def:
        log.error("Unknown LoRA: %s", lora_name)
        return {"error": f"Unknown LoRA: {lora_name}"}

    target = target_override or lora_def["target_clips"]
    clip_min, clip_max = lora_def["clip_length"]

    base_dir = Path("/opt/anime-studio/datasets/_motion_loras") / lora_name
    clips_dir = base_dir / "clips"
    originals_dir = base_dir / "originals"
    clips_dir.mkdir(parents=True, exist_ok=True)
    originals_dir.mkdir(parents=True, exist_ok=True)

    log.info("=" * 60)
    log.info("Collecting clips for: %s (%s)", lora_name, lora_def["label"])
    log.info("Target: %d clips, %.0f-%.0fs each", target, clip_min, clip_max)
    log.info("Output: %s", clips_dir)
    log.info("=" * 60)

    # Check existing clips
    existing = list(clips_dir.glob("*.mp4"))
    if len(existing) >= target:
        log.info("Already have %d/%d clips, skipping", len(existing), target)
        return {"lora": lora_name, "existing": len(existing), "downloaded": 0, "status": "complete"}

    needed = target - len(existing)
    log.info("Need %d more clips (have %d)", needed, len(existing))

    # Gather search results from both APIs
    all_results = []
    seen_ids = set()
    avoid = set(lora_def.get("avoid_keywords", []))

    # --- Pexels ---
    if pexels:
        for query in lora_def["queries"]:
            log.info("[Pexels] Searching: '%s'", query)
            results = pexels.search(
                query, per_page=15, min_duration=clip_min, max_duration=clip_max * 3,
            )
            for r in results:
                key = f"pexels_{r['id']}"
                if key not in seen_ids:
                    seen_ids.add(key)
                    all_results.append(r)
            time.sleep(0.5)  # Rate limit courtesy

            if len(all_results) >= needed * 2:
                break  # Enough candidates

    # --- Pixabay ---
    if pixabay:
        for query in lora_def.get("pixabay_queries", lora_def["queries"][:5]):
            log.info("[Pixabay] Searching: '%s'", query)
            results = pixabay.search(query, per_page=15, min_duration=clip_min)
            for r in results:
                key = f"pixabay_{r['id']}"
                if key not in seen_ids:
                    seen_ids.add(key)
                    all_results.append(r)
            time.sleep(0.5)

            if len(all_results) >= needed * 2:
                break

    log.info("Found %d candidate clips from search", len(all_results))

    if dry_run:
        log.info("[DRY RUN] Would download %d clips, skipping", min(needed, len(all_results)))
        for i, r in enumerate(all_results[:needed]):
            log.info("  %d. [%s #%s] %dx%d %.0fs — query: '%s'",
                     i + 1, r["source"], r["id"], r["width"], r["height"],
                     r["duration"], r["query"])
        return {
            "lora": lora_name,
            "candidates": len(all_results),
            "would_download": min(needed, len(all_results)),
            "status": "dry_run",
        }

    # Shuffle for variety, then download + trim
    random.shuffle(all_results)

    downloaded = 0
    failed = 0
    captions = {}
    clip_index = len(existing)  # Continue numbering from existing

    for result in all_results:
        if downloaded >= needed:
            break

        src = result["source"]
        vid_id = result["id"]
        filename = f"{lora_name}_{src}_{vid_id}"
        orig_path = originals_dir / f"{filename}_orig.mp4"
        clip_path = clips_dir / f"{filename}.mp4"

        if clip_path.exists():
            log.info("  Already exists: %s", clip_path.name)
            downloaded += 1
            continue

        # Download original
        log.info("  Downloading [%s #%s] %dx%d %.0fs...",
                 src, vid_id, result["width"], result["height"], result["duration"])
        if not download_file(result["url"], orig_path):
            failed += 1
            continue

        # Trim to target length
        if trim_clip(orig_path, clip_path, clip_min, clip_max):
            caption = generate_caption(lora_def, clip_index)
            captions[clip_path.name] = {
                "caption": caption,
                "source": src,
                "source_id": vid_id,
                "query": result["query"],
                "original_duration": result["duration"],
            }
            clip_index += 1
            downloaded += 1
            log.info("  OK: %s — '%s'", clip_path.name, caption)
        else:
            failed += 1
            log.warning("  SKIP: trim failed for %s", orig_path.name)

        time.sleep(0.3)  # Be polite to APIs

    # Save captions
    captions_file = base_dir / "captions.json"
    existing_captions = {}
    if captions_file.exists():
        existing_captions = json.loads(captions_file.read_text())
    existing_captions.update(captions)
    captions_file.write_text(json.dumps(existing_captions, indent=2))

    # Build manifest
    all_clips = sorted(clips_dir.glob("*.mp4"))
    manifest = {
        "lora_name": lora_name,
        "label": lora_def["label"],
        "priority": lora_def["priority"],
        "total_clips": len(all_clips),
        "target_clips": target,
        "clip_length_range": [clip_min, clip_max],
        "min_resolution": lora_def["min_resolution"],
        "training_ready": len(all_clips) >= target,
        "clips": [c.name for c in all_clips],
        "caption_template": lora_def["caption_template"],
    }
    (base_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    total_clips = len(all_clips)
    status = "complete" if total_clips >= target else "partial"
    log.info("Result: %d/%d clips collected (%d failed) — %s",
             total_clips, target, failed, status)

    return {
        "lora": lora_name,
        "total_clips": total_clips,
        "downloaded": downloaded,
        "failed": failed,
        "status": status,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Collect stock video clips for motion LoRA training",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --all                     Collect all Priority 1 LoRAs
  %(prog)s --all --priority 2        Collect Priority 1 + 2 LoRAs
  %(prog)s --lora walk_cycle         Collect walk clips only
  %(prog)s --lora walk_cycle --dry-run  Search without downloading
  %(prog)s --list                    Show available LoRA definitions
        """,
    )
    parser.add_argument("--lora", type=str, help="Specific LoRA to collect clips for")
    parser.add_argument("--all", action="store_true", help="Collect for all Priority 1 LoRAs")
    parser.add_argument("--priority", type=int, default=1,
                        help="Max priority level to collect (with --all). Default: 1")
    parser.add_argument("--target", type=int, help="Override target clip count")
    parser.add_argument("--dry-run", action="store_true", help="Search only, don't download")
    parser.add_argument("--list", action="store_true", help="List available LoRA definitions")

    args = parser.parse_args()

    if args.list:
        print("\nAvailable Motion LoRA Definitions:")
        print("-" * 60)
        for name, defn in sorted(LORA_SEARCH_QUERIES.items(), key=lambda x: x[1]["priority"]):
            clip_min, clip_max = defn["clip_length"]
            print(f"  P{defn['priority']}  {name:<20s}  {defn['label']:<25s}  "
                  f"{defn['target_clips']} clips @ {clip_min}-{clip_max}s")
        print()
        return

    if not args.lora and not args.all:
        parser.print_help()
        return

    # Init API clients
    pexels_key = os.environ.get("PEXELS_API_KEY")
    pixabay_key = os.environ.get("PIXABAY_API_KEY")

    if not pexels_key and not pixabay_key:
        log.error("No API keys found. Set at least one of:")
        log.error("  export PEXELS_API_KEY='your_key'  (get at https://www.pexels.com/api/)")
        log.error("  export PIXABAY_API_KEY='your_key'  (get at https://pixabay.com/api/docs/)")
        sys.exit(1)

    pexels = PexelsClient(pexels_key) if pexels_key else None
    pixabay = PixabayClient(pixabay_key) if pixabay_key else None

    sources = []
    if pexels:
        sources.append("Pexels")
    if pixabay:
        sources.append("Pixabay")
    log.info("API sources: %s", " + ".join(sources))

    # Determine which LoRAs to collect
    if args.lora:
        lora_names = [args.lora]
    else:
        lora_names = [
            name for name, defn in sorted(
                LORA_SEARCH_QUERIES.items(), key=lambda x: x[1]["priority"]
            )
            if defn["priority"] <= args.priority
        ]

    log.info("Collecting clips for %d LoRA(s): %s", len(lora_names), ", ".join(lora_names))

    # Run collection
    results = []
    for lora_name in lora_names:
        result = collect_clips_for_lora(
            lora_name, pexels, pixabay,
            target_override=args.target,
            dry_run=args.dry_run,
        )
        results.append(result)

    # Summary
    print("\n" + "=" * 60)
    print("COLLECTION SUMMARY")
    print("=" * 60)
    for r in results:
        status_icon = {
            "complete": "[OK]",
            "partial": "[!!]",
            "dry_run": "[--]",
        }.get(r.get("status", ""), "[??]")
        total = r.get("total_clips", r.get("candidates", r.get("would_download", "?")))
        target = LORA_SEARCH_QUERIES[r["lora"]]["target_clips"]
        print(f"  {status_icon} {r['lora']:<20s}  {total}/{target} clips")

    # Check training readiness
    ready = [r for r in results if r.get("status") == "complete"]
    if ready and not args.dry_run:
        print(f"\n{len(ready)} LoRA(s) ready for training!")
        print("Next steps:")
        print("  1. Review clips in /opt/anime-studio/datasets/_motion_loras/")
        print("  2. Remove any bad clips (wrong motion, static shots, etc.)")
        print("  3. Upload to RunComfy or WaveSpeed for WAN 2.2 14B training")
        print("  4. Or use DIY HuggingFace training scripts")
        print("  5. After training, add to /opt/anime-studio/config/lora_catalog.yaml")


if __name__ == "__main__":
    main()
