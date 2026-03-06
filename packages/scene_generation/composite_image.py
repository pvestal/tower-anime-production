"""Composite image generator for multi-character shots.

Generates a single still image containing two characters using SD1.5 + IP-Adapter
regional conditioning. Each character gets their own IP-Adapter reference image
applied to their region of the canvas, producing a composite source frame that
FramePack I2V can then animate.

Pipeline:
  1. Pick best approved reference image per character
  2. Build ComfyUI workflow with regional IP-Adapter (left/right masks)
  3. Submit and poll until complete
  4. Return path to generated composite image

Mask files (pre-generated, stored in ComfyUI/input/):
  - mask_left_half.png: left half white, right half black (544x704)
  - mask_right_half.png: right half white, left half black (544x704)
"""

import json
import logging
import random
import shutil
import time
import urllib.request
from pathlib import Path

from packages.core.config import BASE_PATH, COMFYUI_URL, COMFYUI_INPUT_DIR, COMFYUI_OUTPUT_DIR

logger = logging.getLogger(__name__)


def _ensure_masks_exist(width: int = 544, height: int = 704):
    """Create left/right half mask PNGs in ComfyUI input if they don't exist."""
    left_path = Path(COMFYUI_INPUT_DIR) / "mask_left_half.png"
    right_path = Path(COMFYUI_INPUT_DIR) / "mask_right_half.png"
    if left_path.exists() and right_path.exists():
        return
    try:
        from PIL import Image
        import numpy as np
        left = np.zeros((height, width), dtype=np.uint8)
        left[:, :width // 2] = 255
        Image.fromarray(left).save(left_path)
        right = np.zeros((height, width), dtype=np.uint8)
        right[:, width // 2:] = 255
        Image.fromarray(right).save(right_path)
        logger.info(f"Created composite masks: {width}x{height}")
    except Exception as e:
        logger.error(f"Failed to create masks: {e}")


async def pick_best_reference(conn, character_slug: str, project_id: int) -> Path | None:
    """Pick the best approved image for a character as IP-Adapter reference.

    Prefers images with higher quality_score from character_approvals,
    falls back to random approved image from approval_status.json.
    """
    # Try DB approvals with quality score first
    try:
        row = await conn.fetchrow(
            """SELECT image_path FROM character_approvals
               WHERE character_slug = $1 AND project_id = $2 AND status = 'approved'
               ORDER BY quality_score DESC NULLS LAST, created_at DESC
               LIMIT 1""",
            character_slug, project_id,
        )
        if row and row["image_path"]:
            p = Path(row["image_path"])
            if not p.is_absolute():
                p = BASE_PATH / p
            if p.exists():
                return p
    except Exception:
        pass

    # Fallback: pick from approval_status.json
    status_file = BASE_PATH / character_slug / "approval_status.json"
    if not status_file.exists():
        for d in BASE_PATH.iterdir():
            if d.is_dir() and d.name.replace("_", "") == character_slug.replace("_", ""):
                status_file = d / "approval_status.json"
                break
    if not status_file.exists():
        logger.warning(f"No approval_status.json for {character_slug}")
        return None

    with open(status_file) as f:
        statuses = json.load(f)

    approved = [k for k, v in statuses.items() if v == "approved"]
    if not approved:
        logger.warning(f"No approved images for {character_slug}")
        return None

    chosen = random.choice(approved)
    img_dir = BASE_PATH / character_slug / "images"
    if not img_dir.exists():
        img_dir = status_file.parent / "images"
    img_path = img_dir / chosen
    if img_path.exists():
        return img_path

    logger.warning(f"Approved image {chosen} not found on disk for {character_slug}")
    return None


def _copy_to_comfyui_input(src: Path, name: str) -> str:
    """Copy an image to ComfyUI input directory, return the filename."""
    dest = Path(COMFYUI_INPUT_DIR) / name
    shutil.copy2(src, dest)
    return name


def build_composite_workflow(
    prompt: str,
    negative_prompt: str,
    checkpoint_model: str,
    char_a_image: str,
    char_b_image: str,
    width: int = 544,
    height: int = 704,
    steps: int = 30,
    cfg: float = 7.0,
    sampler: str = "dpmpp_2m",
    scheduler: str = "karras",
    seed: int | None = None,
    output_prefix: str = "composite",
) -> tuple[dict, str]:
    """Build a ComfyUI workflow for two-character composite image generation.

    Uses IP-Adapter regional conditioning with pre-generated left/right mask PNGs
    loaded via LoadImageMask. Each character's reference image is applied to their
    half of the canvas.

    Returns (workflow_dict, output_prefix).
    """
    _ensure_masks_exist(width, height)

    if seed is None:
        seed = random.randint(1, 2**31)

    workflow = {}

    # 1: Checkpoint loader
    workflow["1"] = {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": checkpoint_model},
    }

    # 2: IP-Adapter Unified Loader (loads both model and ipadapter)
    workflow["2"] = {
        "class_type": "IPAdapterUnifiedLoader",
        "inputs": {
            "preset": "PLUS (high strength)",
            "model": ["1", 0],
        },
    }

    # 3: Load character A reference image
    workflow["3"] = {
        "class_type": "LoadImage",
        "inputs": {"image": char_a_image, "upload": "image"},
    }

    # 4: Load character B reference image
    workflow["4"] = {
        "class_type": "LoadImage",
        "inputs": {"image": char_b_image, "upload": "image"},
    }

    # 5: Positive prompt
    workflow["5"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": prompt, "clip": ["1", 1]},
    }

    # 6: Negative prompt
    workflow["6"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": negative_prompt, "clip": ["1", 1]},
    }

    # 7: Load left-half mask (for character A)
    workflow["7"] = {
        "class_type": "LoadImageMask",
        "inputs": {"image": "mask_left_half.png", "channel": "red"},
    }

    # 8: Load right-half mask (for character B)
    workflow["8"] = {
        "class_type": "LoadImageMask",
        "inputs": {"image": "mask_right_half.png", "channel": "red"},
    }

    # 9: Regional conditioning for character A (left side)
    workflow["9"] = {
        "class_type": "IPAdapterRegionalConditioning",
        "inputs": {
            "image": ["3", 0],
            "image_weight": 0.8,
            "prompt_weight": 1.0,
            "weight_type": "linear",
            "start_at": 0.0,
            "end_at": 0.80,
            "mask": ["7", 0],
            "positive": ["5", 0],
            "negative": ["6", 0],
        },
    }

    # 10: Regional conditioning for character B (right side)
    workflow["10"] = {
        "class_type": "IPAdapterRegionalConditioning",
        "inputs": {
            "image": ["4", 0],
            "image_weight": 0.8,
            "prompt_weight": 1.0,
            "weight_type": "linear",
            "start_at": 0.0,
            "end_at": 0.80,
            "mask": ["8", 0],
            "positive": ["9", 1],  # Chain from region A
            "negative": ["9", 2],
        },
    }

    # 11: Combine regional IP-Adapter params
    workflow["11"] = {
        "class_type": "IPAdapterCombineParams",
        "inputs": {
            "params_1": ["9", 0],
            "params_2": ["10", 0],
        },
    }

    # 12: Apply combined IP-Adapter
    workflow["12"] = {
        "class_type": "IPAdapterFromParams",
        "inputs": {
            "model": ["2", 0],
            "ipadapter": ["2", 1],
            "ipadapter_params": ["11", 0],
            "combine_embeds": "concat",
            "embeds_scaling": "K+V",
        },
    }

    # 13: Empty latent
    workflow["13"] = {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": width, "height": height, "batch_size": 1},
    }

    # 14: KSampler
    workflow["14"] = {
        "class_type": "KSampler",
        "inputs": {
            "seed": seed,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": sampler,
            "scheduler": scheduler,
            "denoise": 1.0,
            "model": ["12", 0],
            "positive": ["10", 1],  # Final chained positive
            "negative": ["10", 2],  # Final chained negative
            "latent_image": ["13", 0],
        },
    }

    # 15: VAE Decode
    workflow["15"] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["14", 0],
            "vae": ["1", 2],
        },
    }

    # 16: Save Image
    workflow["16"] = {
        "class_type": "SaveImage",
        "inputs": {
            "filename_prefix": output_prefix,
            "images": ["15", 0],
        },
    }

    return workflow, output_prefix


def submit_workflow(workflow: dict) -> str:
    """Submit a workflow to ComfyUI and return the prompt_id."""
    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read())
    return result.get("prompt_id", "")


def poll_completion(prompt_id: str, timeout: int = 300) -> Path | None:
    """Poll ComfyUI until the prompt completes. Return the output image path."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            url = f"{COMFYUI_URL}/history/{prompt_id}"
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=10)
            history = json.loads(resp.read())

            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                for node_id, node_out in outputs.items():
                    images = node_out.get("images", [])
                    if images:
                        img = images[0]
                        subfolder = img.get("subfolder", "")
                        filename = img["filename"]
                        if subfolder:
                            return Path(COMFYUI_OUTPUT_DIR) / subfolder / filename
                        return Path(COMFYUI_OUTPUT_DIR) / filename
                logger.warning(f"Prompt {prompt_id} completed but no images in output")
                return None
        except Exception:
            pass
        time.sleep(3)

    logger.error(f"Prompt {prompt_id} timed out after {timeout}s")
    return None


async def generate_composite_source(
    conn,
    project_id: int,
    characters: list[str],
    scene_prompt: str,
    checkpoint_model: str = "waiIllustriousSDXL_v160.safetensors",
) -> Path | None:
    """Generate a composite image with multiple characters for use as FramePack source.

    Args:
        conn: DB connection
        project_id: Project ID for character lookups
        characters: List of character slugs (first 2 used)
        scene_prompt: Text describing the scene/interaction
        checkpoint_model: SD1.5 checkpoint to use

    Returns:
        Path to the generated composite image, or None on failure.
    """
    if len(characters) < 2:
        logger.warning("generate_composite_source needs at least 2 characters")
        return None

    char_a, char_b = characters[0], characters[1]

    # Get reference images
    ref_a = await pick_best_reference(conn, char_a, project_id)
    ref_b = await pick_best_reference(conn, char_b, project_id)

    if not ref_a or not ref_b:
        logger.error(f"Missing reference images: {char_a}={ref_a}, {char_b}={ref_b}")
        return None

    # Get character design prompts
    design_a = ""
    design_b = ""
    for slug, attr in [(char_a, "a"), (char_b, "b")]:
        row = await conn.fetchrow(
            "SELECT name, design_prompt FROM characters "
            "WHERE REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = $1",
            slug,
        )
        if row:
            name = row["name"]
            design = (row["design_prompt"] or "").strip().rstrip(",. ")
            if attr == "a":
                design_a = f"{name} on the left, {design}"
            else:
                design_b = f"{name} on the right, {design}"

    full_prompt = f"two people, {design_a}, {design_b}, {scene_prompt}, masterpiece, best quality, detailed"
    negative = "worst quality, low quality, blurry, deformed, extra limbs, bad anatomy, three people, crowd, watermark, text"

    ref_a_name = _copy_to_comfyui_input(ref_a, f"composite_ref_{char_a}.png")
    ref_b_name = _copy_to_comfyui_input(ref_b, f"composite_ref_{char_b}.png")

    ts = int(time.time())
    prefix = f"composite_{char_a}_{char_b}_{ts}"

    workflow, _ = build_composite_workflow(
        prompt=full_prompt,
        negative_prompt=negative,
        checkpoint_model=checkpoint_model,
        char_a_image=ref_a_name,
        char_b_image=ref_b_name,
        output_prefix=prefix,
    )

    logger.info(f"Submitting composite workflow: {char_a} + {char_b}")
    prompt_id = submit_workflow(workflow)
    if not prompt_id:
        logger.error("Failed to submit composite workflow")
        return None

    logger.info(f"Composite workflow submitted: {prompt_id}, polling...")
    result = poll_completion(prompt_id, timeout=120)

    if result and result.exists():
        logger.info(f"Composite image generated: {result}")
        return result
    else:
        logger.error(f"Composite generation failed for {char_a} + {char_b}")
        return None


async def generate_simple_keyframe(
    conn,
    project_id: int,
    characters: list[str],
    scene_prompt: str,
    checkpoint_model: str = "waiIllustriousSDXL_v160.safetensors",
    shot_type: str = "medium",
    camera_angle: str = "eye-level",
    extra_loras: list[tuple[str, float]] | None = None,
    controlnet_image: str | None = None,
    controlnet_strength: float = 0.7,
    controlnet_type: str = "openpose",
) -> Path | None:
    """Generate a keyframe image that matches the shot's composition requirements.

    Uses shot_type and camera_angle to drive framing — not just a character portrait.

    Args:
        conn: DB connection
        project_id: Project ID for character lookups
        characters: List of character slugs
        scene_prompt: Text describing the scene
        checkpoint_model: SD1.5/SDXL checkpoint to use
        shot_type: establishing, wide, medium, close-up, action
        camera_angle: eye-level, low-angle, high-angle, dutch, overhead

    Returns:
        Path to generated keyframe image, or None on failure.
    """
    if not characters:
        return None

    # Build character descriptions (kept SHORT — scene prompt drives composition)
    char_names = []
    primary_lora = None
    for slug in characters[:2]:
        row = await conn.fetchrow(
            "SELECT name, design_prompt, lora_path FROM characters "
            "WHERE REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = $1 "
            "AND project_id = $2",
            slug, project_id,
        )
        if row:
            char_names.append(row["name"])
            if not primary_lora and row["lora_path"]:
                primary_lora = row["lora_path"]

    if not char_names:
        # Characters not in DB (extras like "villagers", "corporate_security")
        # Use slug as display name — the scene_prompt already has full descriptions
        char_names = [slug.replace("_", " ").title() for slug in characters[:2]]
        logger.info(f"generate_simple_keyframe: using slug names for {characters[:2]} (not in DB)")

    # Shot-type composition prefixes — tells the model WHAT to draw
    composition_prefix = {
        "establishing": "wide establishing shot, full environment, distant figures, cityscape, panoramic view",
        "wide": "wide shot, full body visible, environment context, dynamic scene",
        "medium": "medium shot, waist-up, character interacting with environment",
        "close-up": "close-up shot, face and upper body, intense expression, dramatic lighting",
        "action": "dynamic action pose, motion blur, dramatic angle, combat scene, intense movement",
    }.get(shot_type, "medium shot")

    # Camera angle modifiers
    angle_modifier = {
        "low-angle": "low angle looking up, imposing, dramatic perspective",
        "high-angle": "high angle looking down, overhead perspective",
        "dutch": "dutch angle, tilted camera, tension, unease",
        "overhead": "birds eye view, top-down perspective",
        "eye-level": "",
    }.get(camera_angle, "")

    # Build prompt: COMPOSITION first, then SCENE ACTION, then character name (not full description)
    # LoRA handles character appearance — prompt should drive the scene
    parts = [composition_prefix]
    if angle_modifier:
        parts.append(angle_modifier)
    parts.append(scene_prompt)
    # Only add character names (not full design_prompt) — LoRA provides appearance
    if len(char_names) > 1:
        parts.append(f"{' and '.join(char_names)}")
    else:
        parts.append(char_names[0])
    parts.append("anime style, detailed, cinematic lighting, masterpiece, best quality")

    full_prompt = ", ".join(parts)

    # Stronger negative for establishing/wide to prevent portrait mode
    negative_parts = ["worst quality, low quality, blurry, deformed, extra limbs, bad anatomy, watermark, text"]
    if shot_type in ("establishing", "wide"):
        negative_parts.append("portrait, headshot, close-up face, bust shot, white background, simple background")
    elif shot_type == "action":
        negative_parts.append("static pose, standing still, portrait, peaceful, calm")

    negative = ", ".join(negative_parts)

    # Resolution based on shot type — landscape for establishing/wide, portrait for rest
    # Illustrious SDXL native resolution
    if shot_type in ("establishing", "wide"):
        kf_width, kf_height = 1216, 832   # landscape
    else:
        kf_width, kf_height = 832, 1216   # portrait

    # LoRA strength — OFF for establishing (env matters), low for wide, normal for close-up
    lora_strength = {
        "establishing": 0.0,  # no LoRA — pure environment
        "wide": 0.3,
        "action": 0.5,
        "medium": 0.7,
        "close-up": 0.85,
    }.get(shot_type, 0.7)

    # Build a simple txt2img workflow with optional LoRA
    ts = int(time.time())
    prefix = f"keyframe_{'_'.join(characters[:2])}_{ts}"

    workflow = {
        "3": {
            "inputs": {
                "seed": ts % (2**31),
                "steps": 25,
                "cfg": 5.0,
                "sampler_name": "euler_ancestral",
                "scheduler": "normal",
                "denoise": 1,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
            "class_type": "KSampler",
        },
        "4": {
            "inputs": {"ckpt_name": checkpoint_model},
            "class_type": "CheckpointLoaderSimple",
        },
        "5": {
            "inputs": {"width": kf_width, "height": kf_height, "batch_size": 1},
            "class_type": "EmptyLatentImage",
        },
        "6": {
            "inputs": {"text": full_prompt, "clip": ["4", 1]},
            "class_type": "CLIPTextEncode",
        },
        "7": {
            "inputs": {"text": negative, "clip": ["4", 1]},
            "class_type": "CLIPTextEncode",
        },
        "8": {
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            "class_type": "VAEDecode",
        },
        "9": {
            "inputs": {"filename_prefix": prefix, "images": ["8", 0]},
            "class_type": "SaveImage",
        },
    }

    # Inject LoRA if available (with shot-type-aware strength)
    if primary_lora:
        lora_file = Path(f"/opt/ComfyUI/models/loras/{primary_lora}")
        if not lora_file.exists():
            lora_file = Path(f"/opt/ComfyUI/models/loras/{primary_lora}.safetensors")
        if lora_file.exists():
            workflow["10"] = {
                "inputs": {
                    "lora_name": lora_file.name,
                    "strength_model": lora_strength,
                    "strength_clip": lora_strength,
                    "model": ["4", 0],
                    "clip": ["4", 1],
                },
                "class_type": "LoraLoader",
            }
            workflow["3"]["inputs"]["model"] = ["10", 0]
            workflow["6"]["inputs"]["clip"] = ["10", 1]
            workflow["7"]["inputs"]["clip"] = ["10", 1]
            logger.info(f"Keyframe: LoRA {lora_file.name} @ {lora_strength} ({shot_type})")

    # Chain extra LoRAs (pose/action/environment) after character LoRA
    if extra_loras:
        # Find the current model/clip source (either node "10" if char LoRA, or "4" if none)
        _has_primary = "10" in workflow
        _prev_node = "10" if _has_primary else "4"
        for _i, (_lora_file, _lora_str) in enumerate(extra_loras):
            _lora_path = Path(f"/opt/ComfyUI/models/loras/{_lora_file}")
            if not _lora_path.exists():
                logger.warning(f"Extra LoRA not found: {_lora_file}")
                continue
            _node_id = str(20 + _i)  # nodes 20, 21, 22...
            workflow[_node_id] = {
                "inputs": {
                    "lora_name": _lora_path.name,
                    "strength_model": _lora_str,
                    "strength_clip": _lora_str,
                    "model": [_prev_node, 0],
                    "clip": [_prev_node, 1],
                },
                "class_type": "LoraLoader",
            }
            workflow["3"]["inputs"]["model"] = [_node_id, 0]
            workflow["6"]["inputs"]["clip"] = [_node_id, 1]
            workflow["7"]["inputs"]["clip"] = [_node_id, 1]
            _prev_node = _node_id
            logger.info(f"Keyframe: extra LoRA {_lora_path.name} @ {_lora_str}")

    # Inject ControlNet if a pose/depth reference is provided
    if controlnet_image:
        controlnet_models = {
            "openpose": "controlnet-openpose-sdxl-1.0.safetensors",
            "depth": "controlnet-depth-sdxl-1.0.safetensors",
        }
        cn_model = controlnet_models.get(controlnet_type)
        cn_path = Path(f"/opt/ComfyUI/models/controlnet/{cn_model}") if cn_model else None
        if cn_path and cn_path.exists():
            workflow["40"] = {
                "inputs": {"control_net_name": cn_model},
                "class_type": "ControlNetLoader",
            }
            workflow["41"] = {
                "inputs": {"image": controlnet_image, "upload": "image"},
                "class_type": "LoadImage",
            }
            workflow["42"] = {
                "inputs": {
                    "strength": controlnet_strength,
                    "start_percent": 0.0,
                    "end_percent": 0.8,
                    "positive": workflow["3"]["inputs"]["positive"],
                    "negative": workflow["3"]["inputs"]["negative"],
                    "control_net": ["40", 0],
                    "image": ["41", 0],
                },
                "class_type": "ControlNetApplyAdvanced",
            }
            workflow["3"]["inputs"]["positive"] = ["42", 0]
            workflow["3"]["inputs"]["negative"] = ["42", 1]
            logger.info(f"Keyframe ControlNet: {controlnet_type} @ {controlnet_strength}")

    logger.info(f"Submitting simple keyframe workflow for {characters[:2]}")
    prompt_id = submit_workflow(workflow)
    if not prompt_id:
        logger.error("Failed to submit keyframe workflow")
        return None

    result = poll_completion(prompt_id, timeout=120)
    if result and result.exists():
        logger.info(f"Simple keyframe generated: {result}")
        return result
    else:
        logger.error(f"Simple keyframe generation failed for {characters[:2]}")
        return None
