#!/usr/bin/env python3
"""
Generate training images using PROJECT-LEVEL style settings from the DB.

Pipeline: Project → generation_style (checkpoint, cfg, steps, resolution, prompts)
          Character → design_prompt (subject description within the project style)

Every character in a project uses the SAME model and settings for visual
consistency across seasons and episodes.
"""

import json
import urllib.request
import random
import time
import shutil
import sys
import os
from pathlib import Path
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

COMFYUI_URL = "http://127.0.0.1:8188"
COMFYUI_OUTPUT = Path("/opt/ComfyUI/output")
_SCRIPT_DIR = Path(__file__).resolve().parent
DATASETS_DIR = _SCRIPT_DIR.parent / "datasets"
WORKFLOW_PATH = _SCRIPT_DIR.parent / "workflows" / "comfyui" / "single_image.json"

_SAMPLER_MAP = {
    "DPM++ 2M Karras": ("dpmpp_2m", "karras"),
    "DPM++ 2M SDE Karras": ("dpmpp_2m_sde", "karras"),
    "DPM++ 2S a Karras": ("dpmpp_2s_ancestral", "karras"),
    "DPM++ SDE Karras": ("dpmpp_sde", "karras"),
    "DPM++ 2M": ("dpmpp_2m", "normal"),
    "Euler a": ("euler_ancestral", "normal"),
    "Euler": ("euler", "normal"),
    "DDIM": ("ddim", "ddim_uniform"),
}


def _normalize_sampler(sampler, scheduler):
    """Convert human-readable sampler names to ComfyUI internal names."""
    if sampler and sampler in _SAMPLER_MAP:
        return _SAMPLER_MAP[sampler]
    return (sampler or "dpmpp_2m", scheduler or "karras")


def build_character_negatives(appearance_data):
    """Build per-character negative prompt terms from appearance_data.

    For non-human characters, adds species-correcting negatives.
    For all characters, converts common_errors into negative terms.
    """
    if not appearance_data:
        return ""

    # Parse if it's a JSON string
    if isinstance(appearance_data, str):
        try:
            appearance_data = json.loads(appearance_data)
        except (json.JSONDecodeError, TypeError):
            return ""

    negatives = []
    species = appearance_data.get("species", "")

    # Non-human characters: add human-rejection negatives
    if "NOT human" in species:
        negatives.extend(["human", "human face", "human skin", "realistic person",
                          "humanoid body", "human proportions"])

    # Star creatures / abstract forms
    if "star-shaped" in species.lower():
        negatives.extend(["child", "boy", "girl", "humanoid", "arms", "legs",
                          "human child", "toddler"])

    # Mushroom creatures
    if "mushroom" in species.lower():
        negatives.extend(["human child", "boy wearing hat", "normal human head"])

    # Common errors → negative terms
    for err in appearance_data.get("common_errors", []):
        err_lower = err.lower()
        if "letter m" in err_lower and "instead of l" in err_lower:
            negatives.append("letter M on cap")
        if "depicted as child" in err_lower or "generates as human child" in err_lower:
            negatives.extend(["child", "teenager", "young boy"])
        if "too short" in err_lower or "too stocky" in err_lower:
            negatives.append("short stocky")

    return ", ".join(dict.fromkeys(negatives))  # dedupe preserving order


POSE_VARIATIONS = [
    "standing pose, front view",
    "three-quarter view, confident stance",
    "side profile, looking ahead",
    "upper body portrait, neutral expression",
    "full body, relaxed pose",
    "close-up portrait, detailed face",
    "dynamic pose, action stance",
    "sitting pose, casual",
    "walking pose, slight movement",
    "arms crossed, assertive stance",
    "looking over shoulder, back turned slightly",
    "leaning forward, curious expression",
    "hands on hips, wide stance",
    "crouching pose, low angle",
    "looking up, low camera angle",
    "looking down, high camera angle",
    "running pose, mid-stride",
    "head tilt, playful expression",
    "dramatic lighting, cinematic angle",
    "from behind, looking back",
]

NSFW_POSE_VARIATIONS = [
    # Lingerie / underwear
    "wearing lace lingerie, standing pose, bedroom setting, soft lighting",
    "wearing sheer negligee, sitting on bed edge, relaxed pose",
    "wearing corset and stockings, confident stance, boudoir lighting",
    "wearing silk robe loosely draped, leaning against doorframe",
    "wearing garter belt and thigh-highs, three-quarter view",
    # Suggestive standing
    "arched back, hand behind head, seductive expression",
    "hip cocked to one side, hand on thigh, sultry look",
    "leaning forward, cleavage visible, playful smirk",
    "stretching pose, arms above head, exposed midriff",
    "standing with back turned, looking over shoulder, bare back",
    # Lying down
    "lying on side, propped on elbow, bedroom setting",
    "lying on back, arms above head, relaxed expression",
    "lying on stomach, chin resting on hands, playful look",
    "sprawled on bed, tangled in sheets, messy hair",
    "reclining on couch, one leg draped over armrest",
    # Sitting / kneeling
    "sitting cross-legged on floor, wearing oversized shirt, bare legs",
    "kneeling pose, hands on thighs, looking up at camera",
    "straddling chair backwards, arms resting on chair back",
    "sitting in bathtub, steam rising, shoulders and collarbone visible",
    "perched on windowsill, backlit silhouette, sheer fabric",
    # Wet / bath
    "emerging from pool, wet hair slicked back, water droplets on skin",
    "standing under shower, head tilted back, eyes closed",
    "wrapped in towel, fresh from bath, steamy bathroom",
    "lying in shallow water, partially submerged, serene expression",
    # Topless / nude artistic
    "topless, arms covering chest, artistic pose, soft studio lighting",
    "nude, curled up pose, knees drawn to chest, vulnerable expression",
    "nude back view, looking over shoulder, dramatic shadows",
    "nude silhouette, backlit, artistic composition",
    "topless, lying on stomach, chin on folded arms, bare back visible",
    "nude side profile, one arm raised, classical art pose",
    # Pin-up style
    "classic pin-up pose, one leg raised, winking",
    "retro pin-up, bent over pose, looking back with surprise",
    "bombshell pose, hand on hip, exaggerated curves, glamour lighting",
    "vintage pin-up sitting pose, legs crossed, coy expression",
    # Intimate / bedroom
    "tangled in bedsheets, messy morning hair, sleepy expression",
    "pulling shirt over head, midriff exposed, caught mid-undress",
    "biting lip, bedroom eyes, close-up portrait, intimate framing",
    "hands running through hair, eyes half-closed, sensual expression",
    "on all fours on bed, looking at camera, inviting expression",
    # Athletic / fitness
    "yoga pose, downward dog, tight workout clothes, athletic body",
    "stretching hamstrings, bent at waist, rear view, gym setting",
    "post-workout, glistening with sweat, sports bra and shorts",
    "pole dance pose, suspended mid-air, athletic and graceful",
    # Cosplay / fantasy
    "bunny girl outfit, fishnet stockings, playful pose",
    "maid outfit, bending forward, feather duster in hand",
    "schoolgirl outfit, skirt lifted slightly by wind, surprised look",
    "nurse costume, seated on desk, legs crossed",
    "catgirl pose, on all fours, tail raised, playful expression",
    "succubus outfit, wings spread, seductive floating pose",
    # BDSM / fetish
    "wearing leather harness, dominant stance, riding crop in hand",
    "hands bound above head with silk ribbon, vulnerable expression",
    "collar and leash, kneeling submissive pose, eyes downcast",
    "latex bodysuit, confident power pose, glossy reflections",
    "blindfolded, hands tied behind back, anticipation expression",
    # Couple / interaction poses
    "pressed against wall, wrists pinned, passionate expression",
    "straddling partner POV, looking down, hands on chest",
    "being carried, legs wrapped around partner, face buried in neck",
    "spooning position, intimate close-up, tender expression",
    "sitting on lap facing viewer, arms around unseen partner",
    # Explicit
    "legs spread, sitting back, exposed, direct eye contact",
    "bent over, rear view, looking back invitingly",
    "on knees, mouth open, tongue out, looking up",
    "missionary position, legs raised, ecstatic expression",
    "riding position, hands on chest, head thrown back",
    "doggy style pose, gripping sheets, pleasure expression",
    "standing against wall, one leg raised, moaning expression",
    "lying back, legs spread wide, self-touching",
    "face down, hips raised, presenting pose",
    "squatting pose, frontal view, fully exposed",
]


def get_db_connection():
    """Connect to anime_production DB via Vault."""
    try:
        import hvac
        token_file = os.path.expanduser("~/.vault-token")
        if os.path.exists(token_file):
            vault_token = open(token_file).read().strip()
            client = hvac.Client(url="http://127.0.0.1:8200", token=vault_token)
            if client.is_authenticated():
                resp = client.secrets.kv.v2.read_secret_version(
                    path="anime/database", mount_point="secret",
                    raise_on_deleted_version=True,
                )
                return psycopg2.connect(
                    host="localhost", database="anime_production",
                    user="patrick", password=resp["data"]["data"]["password"],
                )
    except Exception as e:
        print(f"  Vault: {e}")
    # Fallback
    return psycopg2.connect(
        host="localhost", database="anime_production",
        user="patrick", password=os.getenv("PGPASSWORD", ""),
    )


def load_project_data():
    """Load projects with their styles and characters from DB."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Load projects with their generation style + world_settings style_preamble
    cur.execute("""
        SELECT p.id, p.name as project_name, p.default_style,
               gs.checkpoint_model, gs.positive_prompt_template, gs.negative_prompt_template,
               gs.cfg_scale, gs.steps, gs.width, gs.height, gs.sampler, gs.scheduler,
               ws.style_preamble
        FROM projects p
        JOIN generation_styles gs ON gs.style_name = p.default_style
        LEFT JOIN world_settings ws ON ws.project_id = p.id
        ORDER BY p.name
    """)
    projects = {row["id"]: dict(row) for row in cur.fetchall()}

    # Load characters with design_prompt + appearance_data, grouped by project
    # Slug must strip special chars to match filesystem dirs (e.g. "Bowser Jr." → "bowser_jr")
    cur.execute("""
        SELECT c.name,
               REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') as slug,
               c.design_prompt, c.project_id, c.appearance_data
        FROM characters c
        WHERE c.design_prompt IS NOT NULL AND c.design_prompt != ''
        ORDER BY c.project_id, c.name
    """)
    characters = cur.fetchall()

    conn.close()
    return projects, characters


def build_prompt(project_style, character_design_prompt, pose):
    """Build prompt: style_preamble + project style template + character design + pose."""
    parts = []
    if project_style.get("style_preamble"):
        parts.append(project_style["style_preamble"])
    if project_style.get("positive_prompt_template"):
        parts.append(project_style["positive_prompt_template"])
    parts.append(character_design_prompt)
    parts.append(pose)
    parts.append("solo, 1person, single character, white background, simple background")
    return ", ".join(parts)


LORA_DIR = Path("/opt/ComfyUI/models/loras")


def submit_job(prompt_text, negative_text, prefix, checkpoint,
               cfg, steps, width, height, sampler="euler", scheduler="normal",
               seed=None, character_slug=None):
    """Submit generation job to ComfyUI. Returns (prompt_id, seed, job_params).

    If character_slug is provided and a trained LoRA exists for that character,
    injects a LoraLoader node into the workflow automatically.
    """
    if seed is None:
        seed = random.randint(1, 2**31)
    workflow = json.loads(WORKFLOW_PATH.read_text())
    workflow["1"]["inputs"]["text"] = prompt_text
    workflow["2"]["inputs"]["text"] = negative_text
    workflow["4"]["inputs"]["ckpt_name"] = checkpoint
    workflow["3"]["inputs"]["seed"] = seed
    workflow["3"]["inputs"]["cfg"] = cfg
    workflow["3"]["inputs"]["steps"] = steps
    workflow["3"]["inputs"]["sampler_name"] = sampler
    workflow["3"]["inputs"]["scheduler"] = scheduler
    workflow["5"]["inputs"]["width"] = width
    workflow["5"]["inputs"]["height"] = height
    workflow["7"]["inputs"]["filename_prefix"] = prefix

    # Inject LoraLoader if a trained LoRA exists for this character
    lora_name = None
    if character_slug:
        lora_file = LORA_DIR / f"{character_slug}_lora.safetensors"
        if lora_file.exists():
            lora_name = lora_file.name
            # Add LoraLoader node (node "8") between checkpoint and KSampler/CLIP
            workflow["8"] = {
                "inputs": {
                    "lora_name": lora_name,
                    "strength_model": 0.8,
                    "strength_clip": 0.8,
                    "model": ["4", 0],
                    "clip": ["4", 1],
                },
                "class_type": "LoraLoader",
                "_meta": {"title": "LoRA Loader"},
            }
            # Rewire: KSampler model input → LoraLoader output
            workflow["3"]["inputs"]["model"] = ["8", 0]
            # Rewire: CLIP text encoders → LoraLoader CLIP output
            workflow["1"]["inputs"]["clip"] = ["8", 1]
            workflow["2"]["inputs"]["clip"] = ["8", 1]
            print(f"    [LoRA] Using {lora_name} (strength 0.8)")

    # Inject IP-Adapter if reference images exist for this character
    if character_slug:
        ref_dir = DATASETS_DIR / character_slug / "reference_images"
        ipadapter_model = Path("/opt/ComfyUI/models/ipadapter/ip-adapter-plus_sd15.safetensors")
        clip_vision_model = Path("/opt/ComfyUI/models/clip_vision/CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors")
        if ref_dir.exists() and ipadapter_model.exists() and clip_vision_model.exists():
            ref_images = sorted(ref_dir.glob("*.png")) + sorted(ref_dir.glob("*.jpg"))
            if ref_images:
                ref_img = random.choice(ref_images)
                # Copy reference to ComfyUI input
                comfyui_input = Path("/opt/ComfyUI/input")
                ref_dest = comfyui_input / f"ref_{character_slug}.png"
                if not ref_dest.exists() or ref_dest.stat().st_mtime < ref_img.stat().st_mtime:
                    shutil.copy2(ref_img, ref_dest)

                # Determine model source (LoRA output or checkpoint)
                model_source = ["8", 0] if lora_name else ["4", 0]

                # Load reference image
                workflow["20"] = {
                    "inputs": {"image": ref_dest.name, "upload": "image"},
                    "class_type": "LoadImage",
                }
                # IP-Adapter Unified Loader
                workflow["21"] = {
                    "inputs": {
                        "preset": "PLUS (high strength)",
                        "model": model_source,
                    },
                    "class_type": "IPAdapterUnifiedLoader",
                }
                # IP-Adapter Apply
                workflow["22"] = {
                    "inputs": {
                        "weight": 0.95,
                        "weight_type": "linear",
                        "combine_embeds": "concat",
                        "start_at": 0.0,
                        "end_at": 0.85,
                        "embeds_scaling": "K+V",
                        "model": ["21", 0],
                        "ipadapter": ["21", 1],
                        "image": ["20", 0],
                    },
                    "class_type": "IPAdapterAdvanced",
                }
                # Rewire KSampler to use IP-Adapter output model
                workflow["3"]["inputs"]["model"] = ["22", 0]
                print(f"    [IP-Adapter] ref={ref_img.name} weight=0.9")

    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt", data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req)
    prompt_id = json.loads(resp.read()).get("prompt_id", "")

    job_params = {
        "seed": seed,
        "full_prompt": prompt_text,
        "negative_prompt": negative_text,
        "checkpoint_model": checkpoint,
        "cfg_scale": cfg,
        "steps": steps,
        "sampler": sampler,
        "scheduler": scheduler,
        "width": width,
        "height": height,
        "comfyui_prompt_id": prompt_id,
        "lora": lora_name,
    }
    return prompt_id, seed, job_params


def wait_for_completion(prompt_id, timeout=180):
    """Poll ComfyUI until job completes. Returns output filenames on success."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = urllib.request.urlopen(f"{COMFYUI_URL}/history/{prompt_id}")
            history = json.loads(resp.read())
            if prompt_id in history and history[prompt_id].get("outputs"):
                # Extract actual output filenames from ComfyUI history
                filenames = []
                for node_out in history[prompt_id]["outputs"].values():
                    for img in node_out.get("images", []):
                        filenames.append(img["filename"])
                return filenames
        except Exception:
            pass
        time.sleep(2)
    return None


def copy_to_dataset(slug, filenames, design_prompt, job_params=None,
                    project_name=None, character_name=None, pose=None):
    """Copy specific generated images to dataset with SSOT caption and metadata sidecar."""
    dataset_images = DATASETS_DIR / slug / "images"
    dataset_images.mkdir(parents=True, exist_ok=True)
    copied = 0

    for fname in filenames:
        src = COMFYUI_OUTPUT / fname
        if not src.exists():
            continue
        # Timestamp + random suffix for guaranteed uniqueness across runs
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        rand_suffix = f"{random.randint(1000, 9999)}"
        unique_name = f"gen_{slug}_{ts}_{rand_suffix}.png"
        dest = dataset_images / unique_name
        shutil.copy2(src, dest)
        dest.with_suffix(".txt").write_text(design_prompt)

        if job_params:
            meta = {
                **job_params,
                "design_prompt": design_prompt,
                "pose": pose or "",
                "project_name": project_name or "",
                "character_name": character_name or "",
                "source": "comfyui_generation",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            dest.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))

        copied += 1
        # Clean up ComfyUI output after copying
        src.unlink(missing_ok=True)
    return copied


def main():
    dry_run = "--dry-run" in sys.argv
    nsfw_mode = "--nsfw" in sys.argv
    target = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 10
    only_char = None
    forced_seed = None
    prompt_override = None
    exact_count = None  # --count=N means "generate exactly N", ignoring approval counts
    feedback_negative = None  # Additional negative prompt terms from rejection feedback
    for arg in sys.argv[1:]:
        if arg.startswith("--character="):
            only_char = arg.split("=", 1)[1]
        elif arg.startswith("--seed="):
            forced_seed = int(arg.split("=", 1)[1])
        elif arg.startswith("--prompt-override="):
            prompt_override = arg.split("=", 1)[1]
        elif arg.startswith("--count="):
            exact_count = int(arg.split("=", 1)[1])
        elif arg.startswith("--feedback-negative="):
            feedback_negative = arg.split("=", 1)[1]

    pose_pool = NSFW_POSE_VARIATIONS if nsfw_mode else POSE_VARIATIONS
    if nsfw_mode:
        print("  [NSFW] Using NSFW pose variations")

    print("Loading project SSOT from database...")
    projects, characters = load_project_data()
    print(f"  {len(projects)} projects with generation styles")
    print(f"  {len(characters)} characters with design_prompts")

    # Deduplicate characters (some appear in multiple projects — keep longest design_prompt)
    char_map = {}
    for c in characters:
        slug = c["slug"]
        if only_char and slug != only_char:
            continue
        existing = char_map.get(slug)
        if not existing or len(c["design_prompt"] or "") > len(existing["design_prompt"] or ""):
            char_map[slug] = dict(c)

    # Build generation plan: project → characters needing images
    plan = {}  # project_id → { project_info, characters: [{char, need}] }
    for slug, char in sorted(char_map.items()):
        pid = char["project_id"]
        if pid not in projects:
            continue

        if exact_count is not None:
            # --count=N: generate exactly N images, ignore approval status
            need = exact_count
            approved = 0
        else:
            # Legacy target mode: generate until N approved
            status_file = DATASETS_DIR / slug / "approval_status.json"
            approved = 0
            if status_file.exists():
                statuses = json.load(open(status_file))
                approved = sum(1 for v in statuses.values() if v == "approved")

            need = max(0, target - approved)
            if need <= 0:
                continue

        if pid not in plan:
            plan[pid] = {"project": projects[pid], "characters": []}
        plan[pid]["characters"].append({
            "name": char["name"], "slug": slug,
            "design_prompt": char["design_prompt"],
            "appearance_data": char.get("appearance_data"),
            "approved": approved, "need": need,
        })

    if not plan:
        print("All characters have enough approved images!")
        return

    total_jobs = sum(c["need"] for p in plan.values() for c in p["characters"])
    print(f"\n{'='*70}")
    print(f"  PROJECT-DRIVEN IMAGE GENERATION")
    print(f"  Target: {target} approved per character | Total: {total_jobs} images")
    print(f"{'='*70}")

    for pid, info in sorted(plan.items(), key=lambda x: x[1]["project"]["project_name"]):
        proj = info["project"]
        print(f"\n  PROJECT: {proj['project_name']}")
        print(f"    Model: {proj['checkpoint_model']}")
        print(f"    Style: {proj['default_style']} | CFG {proj['cfg_scale']} | {proj['steps']} steps | {proj['width']}x{proj['height']}")
        for ch in info["characters"]:
            print(f"      {ch['name']:20s}  {ch['approved']}/{target} approved, need {ch['need']}")
            print(f"        design: {ch['design_prompt'][:80]}...")

    if dry_run:
        print(f"\n  [DRY RUN] No images generated.")
        return

    print(f"\n  Starting generation...\n")

    total_generated = 0
    for pid, info in sorted(plan.items(), key=lambda x: x[1]["project"]["project_name"]):
        proj = info["project"]
        checkpoint = proj["checkpoint_model"]
        cfg = proj["cfg_scale"]
        steps = proj["steps"]
        width = proj["width"]
        height = proj["height"]
        sampler, scheduler = _normalize_sampler(proj.get("sampler"), proj.get("scheduler"))
        style_positive = proj.get("positive_prompt_template") or ""
        style_negative = proj.get("negative_prompt_template") or "worst quality, low quality, blurry"
        # Feedback loop: append rejection-derived negatives
        if feedback_negative:
            style_negative = f"{style_negative}, {feedback_negative}"
            print(f"  [feedback loop] Added rejection negatives: {feedback_negative[:60]}...")

        print(f"\n{'='*50}")
        print(f"  {proj['project_name']} ({checkpoint})")
        print(f"{'='*50}")

        for ch in info["characters"]:
            slug = ch["slug"]
            print(f"\n  --- {ch['name']} ({ch['need']} images) ---")

            # Per-character negative prompt from appearance_data
            char_neg = build_character_negatives(ch.get("appearance_data"))
            effective_negative = style_negative
            if char_neg:
                effective_negative = f"{style_negative}, {char_neg}"
                print(f"    [character negatives] {char_neg[:80]}...")

            # Build pose list for this character's batch
            if ch["need"] > len(pose_pool):
                # More images than unique poses — repeat each pose evenly, then shuffle
                repeats = (ch["need"] // len(pose_pool)) or 1
                remainder = ch["need"] % len(pose_pool)
                poses = pose_pool * repeats + random.sample(pose_pool, remainder)
                random.shuffle(poses)
            else:
                poses = random.sample(pose_pool, ch["need"])

            for i in range(ch["need"]):
                pose = poses[i]
                effective_prompt = prompt_override if prompt_override else ch["design_prompt"]
                prompt = build_prompt(proj, effective_prompt, pose)
                prefix = f"gen_{slug}_{random.randint(10000, 99999)}"

                # Use forced seed if provided (incrementing for each image)
                use_seed = (forced_seed + i) if forced_seed is not None else None

                print(f"    [{i+1}/{ch['need']}] {pose}... ", end="", flush=True)

                try:
                    prompt_id, seed, job_params = submit_job(
                        prompt, effective_negative, prefix, checkpoint,
                        cfg, steps, width, height, sampler, scheduler,
                        seed=use_seed, character_slug=slug,
                    )
                    filenames = wait_for_completion(prompt_id)
                    if filenames:
                        copied = copy_to_dataset(
                            slug, filenames, ch["design_prompt"],
                            job_params=job_params,
                            project_name=proj["project_name"],
                            character_name=ch["name"],
                            pose=pose,
                        )
                        total_generated += 1
                        print(f"done (seed={seed}, copied {copied})")
                    else:
                        print("timeout")
                except Exception as e:
                    print(f"error: {e}")

    print(f"\n{'='*70}")
    print(f"  COMPLETE: {total_generated}/{total_jobs} images generated")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
