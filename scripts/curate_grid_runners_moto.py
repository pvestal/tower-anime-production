#!/usr/bin/env python3
"""Curate Grid Runners motorcycle batch into LoRA training dataset.

Copies all gr_moto_batch_* outputs into datasets/grid_runners_lightcycle/images/
with booru-style captions for Illustrious SDXL LoRA training.

Run after the batch completes:
    python3 scripts/curate_grid_runners_moto.py
"""

import json
import re
from pathlib import Path
from shutil import copy2

COMFYUI_OUTPUT = Path("/opt/ComfyUI/output")
DATASET_DIR = Path("/opt/anime-studio/datasets/grid_runners_lightcycle/images")
KEYFRAMES_DIR = Path("/home/patrick/Documents/grid-runners/keyframes")

# Trigger word for the LoRA
TRIGGER = "gr_lightcycle"

# Base tags common to all
BASE_TAGS = "cyberpunk motorcycle, futuristic bike, concept art, neon glow, dark background"


def curate():
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    KEYFRAMES_DIR.mkdir(parents=True, exist_ok=True)

    # Find all outputs across all batches
    patterns = [
        "grid_runners_moto_0[01236]_00001_.png",  # initial good ones
        "gr_moto_batch_*_00001_.png",               # v1 batch
        "gr_v2_detail_*_00001_.png",                 # v2 detail close-ups
        "gr_v2_rider_*_00001_.png",                  # v2 rider + bike
        "gr_v2_action_*_00001_.png",                 # v2 action scenes
    ]
    all_files = []
    for pat in patterns:
        found = sorted(COMFYUI_OUTPUT.glob(pat))
        print(f"  {pat}: {len(found)} files")
        all_files.extend(found)

    copied = 0
    for f in all_files:
        dest_img = DATASET_DIR / f.name
        if dest_img.exists():
            continue

        # Copy to dataset
        copy2(f, dest_img)
        # Copy to keyframes dir too
        copy2(f, KEYFRAMES_DIR / f.name)

        # Write caption with trigger word — vary by block
        name = f.name
        if "detail" in name:
            tags = f"{TRIGGER}, cyberpunk motorcycle detail, mechanical close-up, LED lights, chrome, rubber tire, neon glow, sharp focus"
        elif "rider" in name:
            tags = f"{TRIGGER}, cyberpunk motorcycle, tall woman rider, tight bodysuit, samurai sword, helmet, neon rain, concept art"
        elif "action" in name:
            tags = f"{TRIGGER}, cyberpunk motorcycle action, racing, drifting, rain, smoke, neon trails, dynamic, concept art"
        else:
            tags = f"{TRIGGER}, {BASE_TAGS}"
        caption_file = dest_img.with_suffix(".txt")
        caption_file.write_text(tags)

        copied += 1

    total = len(list(DATASET_DIR.glob("*.png")))
    print(f"Copied {copied} new images")
    print(f"Total dataset: {total} images in {DATASET_DIR}")
    print(f"Trigger word: '{TRIGGER}'")


if __name__ == "__main__":
    curate()
