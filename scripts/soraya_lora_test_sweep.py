#!/usr/bin/env python3
"""Soraya LoRA Test Sweep — generate keyframes for all untested LoRAs.

Reads the LoRA catalog, finds LoRAs not yet tested with Soraya,
and queues keyframe generation for each. Uses the convergence loop's
explicit prompt overrides and learned negatives.

Usage:
    # Dry run — list what would be generated
    python scripts/soraya_lora_test_sweep.py --dry-run

    # Generate for camera/cinematic LoRAs only
    python scripts/soraya_lora_test_sweep.py --category camera --seeds 3

    # Generate all untested, max 50 total
    python scripts/soraya_lora_test_sweep.py --limit 50

    # Only video LoRA pairs
    python scripts/soraya_lora_test_sweep.py --type video_pairs

    # Only image LoRA categories
    python scripts/soraya_lora_test_sweep.py --type image_loras
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from packages.core.config import BASE_PATH
from packages.core.generation import generate_batch
from packages.lora_training.feedback import get_feedback_negatives

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

CHARACTER_SLUG = "soraya"
PROJECT_ID = 66

# LoRAs already tested with Soraya (from generation_history)
ALREADY_TESTED = {
    "anal_reverse_cowgirl_pov", "assertive_cowgirl", "bukkake", "casting_doggy",
    "combo_hj_bj", "cowgirl", "doggy_back", "doggy_front", "double_blowjob",
    "facial", "from_behind", "licking_lips", "lips_bj", "massage_tits",
    "missionary", "mouthful", "panties_aside", "pov_cowgirl", "pov_doggystyle",
    "pov_fellatio", "pov_insertion", "prone_bone", "reverse_cowgirl", "sensual_bj",
    "sex_from_behind_v2", "side_transition", "softcore_photoshoot", "spooning",
    "squatting_cowgirl", "titjob",
}

# Skip these — not applicable to Soraya
SKIP_LORAS = {
    "furry_nsfw_general", "furry_transformation",  # furry-only
}

# Tier → content rating gate
TIER_RATING = {
    "universal": "G",
    "wholesome": "G",
    "mature": "R",
    "explicit": "XXX",
    "furry_explicit": "XXX",
}


def load_catalog():
    import yaml
    catalog_path = Path(__file__).resolve().parent.parent / "config" / "lora_catalog.yaml"
    with open(catalog_path) as f:
        return yaml.safe_load(f)


def get_explicit_prompts():
    """Unambiguous prompt overrides for LoRAs (from convergence loop + new)."""
    return {
        # Existing tested poses (for reference)
        "cowgirl": "woman on top, straddling partner, cowgirl riding position, nude, explicit sexual intercourse",
        "assertive_cowgirl": "woman on top, dominant straddling, pinning partner down, aggressive riding, nude, explicit",
        # New untested video LoRA pairs
        "dr34ml4y": "woman in sensual nude pose, explicit, high quality, masterpiece, best quality",
        "general_nsfw": "woman in sensual nude pose, alluring, confident stance, full body, glamour lighting",
        "penis_enhancer": "woman with man, explicit sex scene, anatomically detailed, close-up",
        "pussy_asshole_closeup": "extreme close-up of female anatomy, explicit detail, nude",
        "nsfw_group_girls": "multiple women together, lesbian scene, intimate touching, nude, explicit",
        "seductive_turns": "woman turning and walking away seductively, looking over shoulder, swaying hips",
        # Camera/cinematic
        "camera_push_in": "woman standing in elegant room, camera pushing in slowly, cinematic",
        "camera_rotation": "woman posing confidently, camera rotating around her, full body",
        "orbit_v2": "woman standing center frame, 360 degree camera orbit, dramatic lighting",
        "rotation_360": "woman in elegant pose, full rotation view, fashion shoot",
        "turntable_360": "woman modeling outfit, turntable rotation, studio lighting",
        "lazy_susan": "woman seated at table, lazy rotation around her, intimate setting",
        "drone_shot": "woman on rooftop or balcony, aerial drone view descending, cinematic",
        "tilt_down": "dramatic low angle looking up at woman, power pose, cinematic lighting",
        "eyes_in": "extreme close-up zoom into woman's eyes, dramatic, expressive gaze",
        "face_to_feet": "camera sweeping from woman's face down to feet, full body reveal",
        "forward_flight": "woman walking forward, chase camera following, dynamic movement",
        "set_reveal": "camera zooming out to reveal woman in elaborate room, establishing shot",
        "cinematic_smash_cut": "woman in dramatic pose, sharp cinematic framing, high contrast",
        "cinematic_flare": "woman backlit with lens flare, golden hour, atmospheric",
        "hard_cut": "woman in dynamic pose, sharp cinematic composition, dramatic lighting",
        # Action/motion
        "catwalk": "woman doing model strut on runway, fashion walk, confident posture, high heels",
        "hip_sway_i2v": "woman swaying hips side to side, sensual dance movement, standing",
        "hip_swing": "woman swinging hips rhythmically, dance movement, confident",
        "tiktok_dance": "woman doing hip dance moves, fun expression, dance pose, dynamic",
        "pixel_walk": "woman walking naturally, casual stride, street setting",
        "jumpscare": "woman rushing toward camera, dramatic close-up, intense expression",
        "fight": "woman in fighting stance, fists raised, martial arts pose, fierce expression",
        "explosion": "woman standing with explosion in background, action scene, dramatic",
        "atomic_explosion": "woman silhouetted against massive mushroom cloud, apocalyptic",
        "bullet_time": "woman in mid-motion frozen pose, bullet time slow motion effect",
        "slap": "woman mid-slap, open palm strike, aggressive expression",
        "transformation": "woman mid-transformation, morphing effect, dramatic lighting",
        "outfit_transform": "woman in ornate outfit, costume reveal, magical sparkle effect",
        "timelapse": "woman sitting still while background changes rapidly, timelapse effect",
        # Style
        "retro_90s_anime": "woman in retro 90s anime style, VHS grain, cel shading, nostalgic",
        "live2d_background": "woman with parallax Live2D background effect, layered depth",
        "sigma_face": "woman with intense confident expression, meme sigma stare, close-up",
        "anguish_wail": "woman crying dramatically, tears streaming, emotional anguish, expressive",
        "transition_v2": "woman's face transitioning between expressions, smooth morph",
        # Image LoRA categories
        "position_ass_ride": "woman riding cowgirl position, straddling, nude, explicit",
        "position_doggy": "woman on hands and knees, doggy style, nude, explicit",
        "position_counter_doggy": "woman bent over kitchen counter, sex from behind, explicit",
        "position_squatting_doggy": "woman in squatting doggy position, low crouch, explicit",
        "position_prone_face_cam": "woman lying prone, face toward camera, POV, nude",
        "position_wall_sex": "woman pressed against wall, standing sex, lifted leg, explicit",
        "position_standing_69": "woman in standing 69 position, acrobatic, explicit",
        "position_spitroast": "woman between two partners, spitroast position, explicit",
        "position_breeding": "woman in breeding position, legs up, missionary variant, explicit",
        "position_straddle_back": "woman straddling from behind view, back visible, explicit",
        "position_mating_press": "woman in mating press position, legs pushed back, explicit",
        "position_mmf": "woman with two male partners, threesome, explicit",
        "choking_throat_grab": "man grabbing woman's throat during sex, POV, dominant, rough",
        "oral_deepthroat_doggy": "woman giving deepthroat while in doggy position, explicit",
        "oral_choking_doggy": "woman being face-fucked in doggy position, rough, explicit",
        "oral_side_bj": "side view of woman giving blowjob, throatfuck, explicit",
        "oral_face_fucking": "woman being face-fucked, rough oral, explicit",
        "oral_fingering": "woman being fingered during sex, explicit foreplay",
        "group_orgy": "group sex scene with multiple partners, orgy, explicit",
        "group_grab": "multiple hands grabbing woman's body, group scene, explicit",
        "group_mmmf_doggy": "woman in doggy with multiple male partners, MMMF, explicit",
        "group_mounted_dp": "woman in double penetration, mounted, explicit",
        "group_multiple_males": "woman surrounded by multiple males, gangbang, explicit",
        "facesitting": "woman sitting on partner's face, facesitting, from below view, dominant",
        "monster_interspecies": "monster/demon creature with woman, fantasy interspecies, explicit",
        "monster_cyborg": "cyborg/robot with woman, sci-fi sex, mechanical, explicit",
        "monster_alien": "alien creature with woman, sci-fi interspecies, explicit",
        "style_cyberpunk": "woman in cyberpunk neon-lit setting, futuristic, tech aesthetic",
        "style_nightclub": "woman in dark nightclub setting, dance floor, neon lights, party",
        "style_fantasy": "woman in fantasy medieval setting, magical elements, ornate",
    }


def get_untested_video_pairs(catalog: dict) -> list[dict]:
    """Get video LoRA pairs not yet tested with Soraya."""
    pairs = catalog.get("video_lora_pairs", {})
    untested = []
    for name, config in pairs.items():
        if not isinstance(config, dict):
            continue
        if name in ALREADY_TESTED or name in SKIP_LORAS:
            continue
        tier = config.get("tier", "unknown")
        untested.append({
            "name": name,
            "type": "video_pair",
            "tier": tier,
            "category": _classify_category(name, config),
            "description": config.get("description", ""),
            "high": config.get("high"),
            "low": config.get("low"),
        })
    return untested


def get_untested_image_loras(catalog: dict) -> list[dict]:
    """Get image LoRAs from categories that haven't been tested."""
    img_cats = catalog.get("image_lora_categories", {})
    untested = []
    for cat_name, cat_data in img_cats.items():
        if not isinstance(cat_data, dict) or "loras" not in cat_data:
            continue
        tier = cat_data.get("tier", "unknown")
        # Skip furry category for Soraya
        if cat_name == "furry":
            continue
        loras = cat_data["loras"]
        if not isinstance(loras, list):
            continue
        for lora_entry in loras:
            if not isinstance(lora_entry, dict):
                continue
            filename = lora_entry.get("filename", "")
            label = lora_entry.get("label", filename)
            if lora_entry.get("video_only"):
                continue  # Skip video-only LoRAs in image category
            untested.append({
                "name": f"{cat_name}_{label.lower().replace(' ', '_')[:30]}",
                "type": "image_lora",
                "tier": tier,
                "category": cat_name,
                "description": label,
                "filename": filename,
                "trigger": lora_entry.get("trigger", ""),
                "strength": lora_entry.get("strength", 0.7),
                "tags": lora_entry.get("tags", []),
            })
    return untested


def _classify_category(name: str, config: dict) -> str:
    """Classify a video LoRA into a category."""
    tier = config.get("tier", "")
    # Camera
    camera_keywords = {"camera", "orbit", "rotation", "turntable", "lazy_susan", "drone",
                       "tilt", "eyes_in", "face_to_feet", "forward_flight", "set_reveal",
                       "cinematic", "hard_cut"}
    if any(kw in name for kw in camera_keywords):
        return "camera"
    # Action
    action_keywords = {"fight", "explosion", "atomic", "bullet", "slap", "transformation",
                       "outfit_transform", "timelapse", "jumpscare"}
    if any(kw in name for kw in action_keywords):
        return "action"
    # Motion/dance
    motion_keywords = {"walk", "catwalk", "dance", "tiktok", "hip_sway", "hip_swing",
                       "seductive", "pixel"}
    if any(kw in name for kw in motion_keywords):
        return "motion"
    # Style
    style_keywords = {"retro", "live2d", "sigma", "anguish", "transition"}
    if any(kw in name for kw in style_keywords):
        return "style"
    # Explicit enhancers
    if tier == "explicit":
        return "explicit"
    return "other"


async def run_sweep(
    dry_run: bool = True,
    category: str = "",
    lora_type: str = "",
    limit: int = 0,
    seeds: int = 3,
    batch_size: int = 10,
):
    catalog = load_catalog()
    prompts = get_explicit_prompts()

    # Collect all untested LoRAs
    all_untested = []
    if lora_type != "image_loras":
        all_untested.extend(get_untested_video_pairs(catalog))
    if lora_type != "video_pairs":
        all_untested.extend(get_untested_image_loras(catalog))

    # Filter by category
    if category:
        all_untested = [l for l in all_untested if l["category"] == category]

    # Apply limit
    if limit > 0:
        all_untested = all_untested[:limit]

    total_gens = len(all_untested) * seeds

    # Summary
    by_category = {}
    by_type = {}
    for l in all_untested:
        by_category.setdefault(l["category"], []).append(l["name"])
        by_type.setdefault(l["type"], []).append(l["name"])

    print(f"\n{'='*60}")
    print(f"SORAYA LORA TEST SWEEP")
    print(f"{'='*60}")
    print(f"Total untested LoRAs: {len(all_untested)}")
    print(f"Seeds per LoRA: {seeds}")
    print(f"Total keyframes to generate: {total_gens}")
    print(f"Batch size: {batch_size}")
    print()

    print("BY TYPE:")
    for t, names in sorted(by_type.items()):
        print(f"  {t}: {len(names)}")

    print("\nBY CATEGORY:")
    for cat, names in sorted(by_category.items()):
        print(f"  {cat} ({len(names)}):")
        for n in names[:8]:
            desc = next((l["description"] for l in all_untested if l["name"] == n), "")
            print(f"    - {n}" + (f" ({desc})" if desc else ""))
        if len(names) > 8:
            print(f"    ... +{len(names)-8} more")

    if dry_run:
        print(f"\n{'='*60}")
        print("DRY RUN — no generations queued")
        print(f"Run without --dry-run to start generating")
        print(f"{'='*60}")
        return

    # Actual generation
    feedback_neg = get_feedback_negatives(CHARACTER_SLUG)
    logger.info(f"Loaded {len(feedback_neg.split(','))} feedback negatives")

    generated = 0
    failed = 0
    batch_queue = []

    for lora_info in all_untested:
        lora_name = lora_info["name"]
        prompt_key = lora_name
        # For image LoRAs, try category-prefixed key
        prompt_text = prompts.get(prompt_key, prompts.get(lora_info.get("category", ""), ""))
        if not prompt_text:
            prompt_text = f"woman in {lora_name.replace('_', ' ')} pose, nude, explicit, high quality"

        for seed_offset in range(seeds):
            seed = 1000 + (all_untested.index(lora_info) * 100) + seed_offset

            batch_queue.append({
                "lora_name": lora_name,
                "prompt": prompt_text,
                "seed": seed,
                "lora_info": lora_info,
            })

            # Process batch
            if len(batch_queue) >= batch_size:
                results = await _process_batch(batch_queue)
                generated += sum(1 for r in results if r)
                failed += sum(1 for r in results if not r)
                batch_queue = []
                logger.info(f"Progress: {generated} generated, {failed} failed, {total_gens - generated - failed} remaining")

    # Process remaining
    if batch_queue:
        results = await _process_batch(batch_queue)
        generated += sum(1 for r in results if r)
        failed += sum(1 for r in results if not r)

    print(f"\n{'='*60}")
    print(f"SWEEP COMPLETE: {generated} generated, {failed} failed")
    print(f"{'='*60}")


async def _process_batch(batch: list[dict]) -> list[bool]:
    """Generate a batch of keyframes sequentially (ComfyUI is the bottleneck)."""
    results = []
    for item in batch:
        try:
            logger.info(f"  [{item['lora_name']}] Generating seed={item['seed']}...")
            result = await generate_batch(
                character_slug=CHARACTER_SLUG,
                count=1,
                seed=item["seed"],
                prompt_override=item["prompt"],
                pose_variation=False,
                fire_events=False,
                include_feedback_negatives=True,
                include_learned_negatives=True,
                lora_name=item["lora_name"],
                pose_tag=item["lora_name"],
                source="lora_sweep",
            )
            if result and result[0].get("images"):
                logger.info(f"  [{item['lora_name']}] OK: {result[0]['images'][0]}")
                results.append(True)
            else:
                logger.warning(f"  [{item['lora_name']}] No images returned")
                results.append(False)
        except Exception as e:
            logger.error(f"  [{item['lora_name']}] Error: {e}")
            results.append(False)
    return results


def main():
    parser = argparse.ArgumentParser(description="Soraya LoRA Test Sweep")
    parser.add_argument("--dry-run", action="store_true", help="List what would be generated without doing it")
    parser.add_argument("--category", default="", help="Filter by category: camera, action, motion, style, explicit, other")
    parser.add_argument("--type", default="", dest="lora_type", help="Filter by type: video_pairs, image_loras")
    parser.add_argument("--limit", type=int, default=0, help="Max number of LoRAs to test")
    parser.add_argument("--seeds", type=int, default=3, help="Seeds per LoRA (default: 3)")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for generation queue")
    args = parser.parse_args()

    asyncio.run(run_sweep(
        dry_run=args.dry_run,
        category=args.category,
        lora_type=args.lora_type,
        limit=args.limit,
        seeds=args.seeds,
        batch_size=args.batch_size,
    ))


if __name__ == "__main__":
    main()
