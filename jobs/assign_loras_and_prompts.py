#!/usr/bin/env python3
"""Assign LoRAs, motion prompts, and action presets to pending shots across all projects.

For trailer content: picks the most visually impactful shots per scene and assigns
appropriate content LoRAs + motion prompts based on scene context and character.

Usage:
    python3 -m jobs.assign_loras_and_prompts [--project ID] [--dry-run]
"""

import asyncio
import asyncpg
import argparse
import random
import re
import yaml
from pathlib import Path

DB_DSN = "postgresql://patrick:RP78eIrW7cI2jYvL5akt1yurE@localhost/anime_production"
CATALOG_PATH = Path("/opt/anime-studio/config/lora_catalog.yaml")

# ──────────────────────────────────────────────────────────────
# Action/LoRA assignment rules per project content rating
# ──────────────────────────────────────────────────────────────

# XXX projects: explicit position LoRAs based on scene context keywords
EXPLICIT_LORA_RULES = [
    # (keywords_in_scene_or_prompt, video_lora_key, image_lora, motion_prompt_template)
    (["blowjob", "oral", "suck", "mouth", "bj", "head"], "combo_hj_bj",
     "deepthroat_doggy.safetensors",
     "head bobbing rhythmically, lips wrapped tight, wet glistening, {char} working mouth up and down"),
    (["sensual", "teasing", "slow oral", "gentle"], "sensual_bj",
     "deepthroat_doggy.safetensors",
     "slow sensual teasing licks, tongue tracing along shaft, eye contact, {char} savoring"),
    (["cowgirl", "riding", "on top", "ride"], "assertive_cowgirl",
     "ass_ride_illustrious.safetensors",
     "{char} riding aggressively, hips bouncing up and down rhythmically, breasts swaying with each thrust"),
    (["reverse", "reverse cowgirl", "facing away"], "reverse_cowgirl",
     "ass_ride_illustrious.safetensors",
     "{char} riding reverse, ass bouncing up and down, back arched, looking over shoulder"),
    (["doggy", "behind", "from behind", "bent over"], "doggy_back",
     "Doggystyle_leaning_on_the_counter.safetensors",
     "thrusting from behind, {char} bracing against surface, body rocking forward with each impact"),
    (["prone", "prone bone", "flat", "face down"], "prone_bone",
     "prone_face_cam_v0_2.safetensors",
     "{char} pressed flat face-down, hips being lifted, deep rhythmic thrusting from above"),
    (["missionary", "spread", "legs open", "on back"], "missionary",
     None,
     "{char} on back, legs spread, body rocking with each thrust, breasts bouncing, breathing heavily"),
    (["spooning", "side", "cuddle", "intimate"], "spooning",
     None,
     "intimate spooning, slow deep thrusts from behind, {char} arching back into partner"),
    (["titjob", "paizuri", "between breasts"], "titjob",
     "NM_FitButt_illv4.safetensors",
     "{char} pressing breasts together around shaft, sliding up and down rhythmically"),
    (["facial", "cum", "finish", "cumshot"], "facial",
     None,
     "{char} face receiving, eyes closed, mouth open, thick ropes landing"),
    (["mouthful", "swallow"], "mouthful",
     None,
     "{char} mouth full, cheeks bulging, swallowing, liquid dripping from corners of lips"),
    (["bukkake", "group finish", "multiple"], "bukkake",
     "group_sex_orgy_illustrious.safetensors",
     "multiple streams hitting {char} face and body simultaneously, overwhelming finish"),
    (["wall", "standing sex", "against wall", "pinned"], "from_behind",
     "sex_wall_1.safetensors",
     "{char} pinned against wall, legs wrapped, deep thrusting, body sliding up and down"),
    (["massage", "oil", "rub"], "massage_tits",
     None,
     "hands kneading and massaging {char} oiled breasts, fingers squeezing, skin glistening"),
    (["panties", "tease", "strip"], "panties_aside",
     None,
     "fingers hooking {char} panties to the side, revealing slowly, teasing entry"),
    (["double blowjob", "two girls", "sharing"], "double_blowjob",
     None,
     "two women taking turns, one licking shaft while other sucks tip, switching rhythm"),
    (["close.*pussy", "close.*ass", "spread", "closeup"], "pussy_asshole_closeup",
     None,
     "extreme close-up, fingers spreading lips apart, glistening wet, pulsing"),
]

# Fury-specific: anthro/furry content
FURRY_LORA_RULES = [
    (["cowgirl", "riding", "on top"], "assertive_cowgirl",
     "human_male_on_furry_female_concept.safetensors",
     "{char} anthro riding aggressively, fur-covered hips bouncing, tail swishing with each thrust"),
    (["blowjob", "oral", "suck"], "combo_hj_bj",
     "human_on_anthro_male_pov_il.safetensors",
     "{char} anthro kneeling, muzzle around shaft, tongue working, furred hands gripping"),
    (["doggy", "behind", "mount"], "doggy_back",
     "human_male_on_furry_female_concept.safetensors",
     "{char} on all fours, tail raised, being mounted from behind, fur rippling with each thrust"),
    (["prone", "pinned"], "prone_bone",
     "human_male_on_furry_female_concept.safetensors",
     "{char} anthro pressed down, tail curled aside, deep mating press, fur compressing"),
    (["missionary", "belly"], "missionary",
     "human_male_on_furry_female_concept.safetensors",
     "{char} anthro on back, legs spread showing belly fur, rhythmic thrusting, panting"),
]

# Camera LoRA rules for SFW projects
CAMERA_LORA_RULES = [
    (["drone", "aerial", "overhead", "bird", "sky"], "wan22_camera/drone_shot_HIGH.safetensors", 0.8),
    (["orbit", "circle", "surround"], "wan22_camera/orbit_v2_HIGH.safetensors", 0.8),
    (["tilt down", "tilt-down", "undershot", "low angle"], "wan22_camera/tilt_down_HIGH.safetensors", 0.8),
    (["360", "turntable", "spin"], "wan22_camera/turntable_360_HIGH.safetensors", 0.7),
    (["rotation", "rotate"], "wan22_camera/camera_rotation_HIGH.safetensors", 0.7),
    (["smash cut", "hard cut", "transition", "scene change"], "wan22_camera/hard_cut_v3_HIGH.safetensors", 0.8),
    (["reveal", "zoom out", "pull back"], "wan22_camera/set_reveal_HIGH.safetensors", 0.8),
    (["eyes", "stare", "intense look", "close-up face"], "wan22_camera/eyes_in_HIGH.safetensors", 0.8),
    (["timelapse", "time-lapse", "passage of time", "fast forward"], "wan22_action/timelapse_HIGH.safetensors", 0.8),
    (["pan", "slow pan", "tracking"], "wan22_camera/camera_push_in.safetensors", 0.7),
    (["zoom", "push in", "dolly"], "wan22_camera/camera_push_in.safetensors", 0.8),
]

# Action LoRA rules for CGS/Scramble City
ACTION_LORA_RULES = [
    (["fight", "combat", "punch", "kick", "attack", "strike", "battle"], "wan22_action/wan_fight.safetensors", 0.7),
    (["explosion", "explode", "detonate", "blast", "bomb", "destroy"], "wan22_action/explosion_HIGH.safetensors", 0.8),
    (["slap", "smack", "hit face"], "wan22_action/slap_HIGH.safetensors", 0.8),
    (["bullet time", "slow motion", "matrix", "time freeze"], "wan22_action/bullet_time_HIGH.safetensors", 0.8),
    (["transform", "morph", "shift", "change form"], "wan22_action/transformation_HIGH.safetensors", 0.8),
    (["cry", "scream", "anguish", "wail", "sob", "despair"], "wan22_action/anguish_wail_HIGH.safetensors", 0.8),
    (["walk", "walking", "approach", "stroll"], "wan22_action/pixel_walk_HIGH.safetensors", 0.6),
    (["dance", "hip", "groove", "sway"], "wan22_action/hip_swing_twist_HIGH.safetensors", 0.7),
    (["catwalk", "strut", "model walk", "runway"], "wan22_action/catwalk.safetensors", 0.7),
]

# Motion prompt templates for SFW shots that have none
MOTION_TEMPLATES = {
    "establishing": "slow cinematic pan across the scene, establishing the environment, atmospheric lighting",
    "wide": "wide shot with subtle camera drift, characters in full frame, ambient motion",
    "medium": "medium shot, subtle character movement, natural body language, slight camera tracking",
    "close-up": "close-up with shallow depth of field, subtle facial animation, micro-expressions",
    "action": "dynamic camera following the action, fast movement, impact frames",
    "detail": "macro close-up, fine detail revealed, slow focus pull",
}


def load_catalog():
    with open(CATALOG_PATH) as f:
        return yaml.safe_load(f) or {}


async def get_effective_lora(conn, char_slug: str, content_rating: str, catalog: dict):
    """Query lora_effectiveness for the best-performing LoRA for this character.

    Returns (lora_name, lora_strength, motion_tier) or (None, None, None).
    """
    try:
        row = await conn.fetchrow("""
            SELECT lora_name, best_lora_strength, best_motion_tier, avg_quality, sample_count
            FROM lora_effectiveness
            WHERE character_slug = $1 AND content_rating = $2 AND sample_count >= 3
            ORDER BY avg_quality DESC NULLS LAST
            LIMIT 1
        """, char_slug, content_rating)
        if row and row["avg_quality"] and row["avg_quality"] > 0.4:
            return row["lora_name"], row["best_lora_strength"] or 0.85, row["best_motion_tier"]
    except Exception:
        pass  # Table may not exist yet
    return None, None, None


def match_explicit_lora(scene_title: str, motion_prompt: str, gen_prompt: str,
                        chars: list, is_furry: bool = False):
    """Match a shot to the best explicit LoRA based on context."""
    text = f"{scene_title} {motion_prompt} {gen_prompt}".lower()
    rules = FURRY_LORA_RULES if is_furry else EXPLICIT_LORA_RULES

    for keywords, video_lora, image_lora, motion_template in rules:
        for kw in keywords:
            if re.search(kw, text):
                char_name = chars[0] if chars else "character"
                motion = motion_template.format(char=char_name)
                return video_lora, image_lora, motion

    return None, None, None


def match_action_lora(motion_prompt: str, gen_prompt: str):
    """Match a shot to action/camera LoRA for SFW content."""
    text = f"{motion_prompt} {gen_prompt}".lower()

    for keywords, lora_file, strength in ACTION_LORA_RULES:
        for kw in keywords:
            if kw in text:
                return lora_file, strength

    for keywords, lora_file, strength in CAMERA_LORA_RULES:
        for kw in keywords:
            if kw in text:
                return lora_file, strength

    return None, None


async def assign_project(conn, project_id: int, catalog: dict, dry_run: bool = False):
    """Assign LoRAs and motion prompts to all pending shots in a project."""
    project = await conn.fetchrow("SELECT * FROM projects WHERE id = $1", project_id)
    if not project:
        print(f"  Project {project_id} not found")
        return

    name = project["name"]
    rating = project["content_rating"]
    is_furry = project_id == 57  # Fury
    is_explicit = rating in ("XXX", "NC-17")
    is_sfw = rating in ("G", "PG", "PG-13")

    print(f"\n{'='*60}")
    print(f"Project: {name} (ID {project_id}, {rating})")
    print(f"{'='*60}")

    pairs = catalog.get("video_lora_pairs", {})

    shots = await conn.fetch("""
        SELECT s.id, s.shot_number, s.shot_type, s.characters_present,
               s.motion_prompt, s.generation_prompt, s.lora_name, s.image_lora,
               sc.title as scene_title, sc.id as scene_id
        FROM shots s JOIN scenes sc ON s.scene_id = sc.id
        WHERE sc.project_id = $1 AND s.status = 'pending' AND s.lora_name IS NULL
        ORDER BY sc.id, s.shot_number
    """, project_id)

    print(f"  Pending shots without LoRA: {len(shots)}")

    assigned = 0
    for shot in shots:
        sid = shot["id"]
        scene = shot["scene_title"]
        motion = shot["motion_prompt"] or ""
        gen = shot["generation_prompt"] or ""
        chars = list(shot["characters_present"] or [])
        shot_type = shot["shot_type"] or "medium"

        video_lora = None
        image_lora = None
        new_motion = None
        new_motion_tier = None
        lora_strength = 0.85

        if is_explicit:
            video_lora_key, image_lora, new_motion = match_explicit_lora(
                scene, motion, gen, chars, is_furry)
            if video_lora_key and video_lora_key in pairs:
                pair = pairs[video_lora_key]
                video_lora = pair["high"]
            elif video_lora_key:
                # Direct filename
                video_lora = f"wan22_nsfw/{video_lora_key}_HIGH.safetensors"

        # Try effectiveness-based assignment before keyword fallback
        if not video_lora and chars:
            eff_lora, eff_strength, eff_tier = await get_effective_lora(
                conn, chars[0], rating, catalog)
            if eff_lora:
                video_lora = eff_lora
                lora_strength = eff_strength
                # Store recommended tier for later use
                if eff_tier:
                    new_motion_tier = eff_tier

        if not video_lora and not is_sfw:
            # For NC-17/R without explicit match, try action LoRAs
            lora_file, strength = match_action_lora(motion, gen)
            if lora_file:
                video_lora = lora_file
                lora_strength = strength

        if not video_lora and is_sfw:
            # SFW: try camera/action LoRAs
            lora_file, strength = match_action_lora(motion, gen)
            if lora_file:
                video_lora = lora_file
                lora_strength = strength

        # Fill in missing motion prompts
        if not motion and not new_motion:
            new_motion = MOTION_TEMPLATES.get(shot_type,
                "subtle natural movement, cinematic framing")

        if video_lora or new_motion:
            assigned += 1
            if not dry_run:
                updates = []
                params = [sid]
                idx = 2

                if video_lora:
                    updates.append(f"lora_name = ${idx}")
                    params.append(video_lora)
                    idx += 1
                    updates.append(f"lora_strength = ${idx}")
                    params.append(lora_strength)
                    idx += 1

                if image_lora:
                    updates.append(f"image_lora = ${idx}")
                    params.append(image_lora)
                    idx += 1
                    updates.append(f"image_lora_strength = ${idx}")
                    params.append(0.7)
                    idx += 1

                if new_motion and not motion:
                    updates.append(f"motion_prompt = ${idx}")
                    params.append(new_motion)
                    idx += 1

                if new_motion_tier:
                    updates.append(f"motion_tier = ${idx}")
                    params.append(new_motion_tier)
                    idx += 1

                if updates:
                    sql = f"UPDATE shots SET {', '.join(updates)} WHERE id = $1"
                    await conn.execute(sql, *params)

            lora_short = (video_lora or "").split("/")[-1][:35] if video_lora else "-"
            print(f"  Shot {shot['shot_number']:2d} | {scene[:30]:30s} | {lora_short:35s}")

    print(f"  => Assigned: {assigned}/{len(shots)} shots")
    return assigned


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=int, help="Single project ID")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    catalog = load_catalog()
    conn = await asyncpg.connect(DB_DSN)

    try:
        projects = [args.project] if args.project else [24, 42, 43, 57, 58, 59, 60, 61]
        total = 0
        for pid in projects:
            count = await assign_project(conn, pid, catalog, args.dry_run)
            total += count or 0

        print(f"\n{'='*60}")
        print(f"Total assigned: {total} shots")
        if args.dry_run:
            print("(DRY RUN — no changes made)")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
