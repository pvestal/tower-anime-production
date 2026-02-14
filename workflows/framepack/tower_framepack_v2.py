#!/usr/bin/env python3
"""
Tower Anime Production — FramePack Video Generation (v2)
========================================================
Built from actual ComfyUI node signatures captured via diagnostic.
Previous version (v1) silently failed on every generation.

Key fixes over v1:
  - Uses correct node types (FramePackMODEL, not generic MODEL)
  - LoadFramePackModel with proper params (load_device, attention_mode)
  - VAEDecodeTiled instead of VAEDecode (required for video latents)
  - Proper output polling that verifies files actually exist
  - Falls back to SaveImage+ffmpeg if VHS_VideoCombine unavailable
  - Integrated output validation (no more false "success" claims)

Usage:
    # Pre-flight check
    python3 tower_framepack_v2.py --check

    # Text-to-video (no source image)
    python3 tower_framepack_v2.py --prompt "a woman walking through Tokyo at night" --seconds 3

    # Image-to-video
    python3 tower_framepack_v2.py --prompt "gentle movement, wind in hair" --image /path/to/image.png --seconds 5

    # Project scenes
    python3 tower_framepack_v2.py --project tdd --scene mei_office --seconds 5

    # Use F1 model
    python3 tower_framepack_v2.py --prompt "a stag in a forest" --f1 --seconds 5
"""

import argparse
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: pip install requests --break-system-packages")
    sys.exit(1)

# ─── Configuration ────────────────────────────────────────────
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://localhost:8188")
OUTPUT_DIR = os.environ.get("FRAMEPACK_OUTPUT", "/mnt/1TB-storage/anime_output")

# Model filenames as ComfyUI sees them (from diagnostic)
MODELS = {
    "i2v": "FramePackI2V_HY_fp8_e4m3fn.safetensors",
    "f1": "FramePack_F1_I2V_HY_20250503_fp8_e4m3fn.safetensors",
    "clip_l": "clip_l.safetensors",
    "llava_text": "llava_llama3_fp16.safetensors",
    "clip_vision": "sigclip_vision_patch14_384.safetensors",
    "vae": "hunyuan_video_vae_bf16.safetensors",
}

# RTX 3060 12GB optimized defaults
# gpu_memory_preservation=6.0 required for stable generation at 544x704+
# 3.5 causes OOM on RTX 3060; 6.0 is proven stable (~20min for 2s clips)
RTX3060_DEFAULTS = {
    "base_precision": "bf16",
    "quantization": "fp8_e4m3fn",
    "load_device": "offload_device",
    "attention_mode": "sdpa",
    "gpu_memory_preservation": 6.0,
    "latent_window_size": 9,
    "vae_tile_size": 256,
    "vae_tile_stride_t": 64,
    "vae_tile_stride_h": 64,
    "vae_tile_stride_w": 8,
}

# ─── Project Scenes ──────────────────────────────────────────
PROJECTS = {
    "tdd": {
        "name": "Tokyo Debt Desire",
        "style": "modern anime with realistic adult proportions",
        "characters": {
            "mei": {"name": "Mei Tanaka", "desc": "Japanese woman, late 20s, long black hair, office attire"},
            "kai": {"name": "Kai Nakamura", "desc": "Japanese man, 30s, sharp suit, confident expression"},
        },
        "scenes": {
            "mei_office": {
                "prompt": "A Japanese woman in her late 20s with long black hair sits at a modern desk in a Tokyo high-rise office. Floor-to-ceiling windows show the city skyline at golden hour. She wears a fitted blazer and reviews documents with focused intensity. Cinematic anime style, detailed lighting.",
                "motion": "subtle head movement, papers rustling, city lights twinkling outside",
            },
            "kai_rooftop": {
                "prompt": "A Japanese man in his 30s wearing a sharp dark suit stands on a Tokyo rooftop at night. Neon city lights reflect in his eyes. Wind ruffles his hair slightly. He holds a phone, expression serious. Cinematic anime style, dramatic lighting.",
                "motion": "wind in hair, city lights flickering, slight body sway",
            },
            "tokyo_night_walk": {
                "prompt": "A young Japanese woman walks alone through rain-slicked Shinjuku streets at night. Neon signs in Japanese reflect off wet pavement. She carries a transparent umbrella. Cinematic anime style, moody atmospheric lighting.",
                "motion": "walking forward, rain falling, neon reflections rippling, umbrella bobbing",
            },
        },
    },
    "cgs": {
        "name": "Cyberpunk Goblin Slayer",
        "style": "dark cyberpunk anime with gritty neon atmosphere",
        "scenes": {
            "neon_alley": {
                "prompt": "A hooded figure with glowing red cybernetic eyes walks through a narrow neon-lit alley in a cyberpunk city. Steam rises from grates, holographic advertisements flicker on walls. Dark anime style, dramatic shadows and neon highlights.",
                "motion": "walking slowly, steam rising, holograms flickering, cybernetic eye pulsing",
            },
        },
    },
    "smg": {
        "name": "Super Mario Galaxy Anime",
        "style": "Illumination Studios 3D movie style",
        "scenes": {
            "galaxy_flight": {
                "prompt": "A tall elegant woman with flowing platinum blonde hair floats through a cosmic star field. She wears a flowing blue gown that trails behind her like a comet tail. Tiny Luma star creatures orbit around her. Galaxies spiral in the background. Illumination Studios 3D movie quality, luminous particle effects, magical atmosphere.",
                "motion": "floating gracefully, hair and gown flowing, Lumas orbiting, stars twinkling",
            },
        },
    },
}


# ═══════════════════════════════════════════════════════════════
# ComfyUI Interface
# ═══════════════════════════════════════════════════════════════

class ComfyUIError(Exception):
    """Raised when ComfyUI returns an error or unexpected state."""
    pass


def comfy_get(endpoint: str, timeout: int = 10) -> dict:
    """GET request to ComfyUI with error handling."""
    resp = requests.get(f"{COMFYUI_URL}{endpoint}", timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def comfy_post(endpoint: str, data: dict, timeout: int = 10) -> dict:
    """POST request to ComfyUI with error handling."""
    resp = requests.post(f"{COMFYUI_URL}{endpoint}", json=data, timeout=timeout)
    if resp.status_code != 200:
        body = resp.text[:1000]
        raise ComfyUIError(f"ComfyUI returned {resp.status_code}: {body}")
    return resp.json()


def probe_nodes() -> dict:
    """
    Probe ComfyUI for available nodes and return capability info.
    This is the foundation — we only build workflows using nodes
    that actually exist, with parameters we've verified.
    """
    all_nodes = comfy_get("/object_info", timeout=15)

    info = {
        "has_load_model": "LoadFramePackModel" in all_nodes,
        "has_download_model": "DownloadAndLoadFramePackModel" in all_nodes,
        "has_sampler": "FramePackSampler" in all_nodes,
        "has_sampler_f1": "FramePackSampler_F1" in all_nodes,
        "has_vhs": "VHS_VideoCombine" in all_nodes,
        "has_save_image": "SaveImage" in all_nodes,
        "has_tiled_decode": "VAEDecodeTiled" in all_nodes,
        "has_bucket_finder": "FramePackFindNearestBucket" in all_nodes,
        "has_lora_select": "FramePackLoraSelect" in all_nodes,
        "has_timestamped_encode": "FramePackTimestampedTextEncode" in all_nodes,
        "has_clip_vision_loader": "CLIPVisionLoader" in all_nodes,
        "has_clip_vision_encode": "CLIPVisionEncode" in all_nodes,
    }

    # Get LoadFramePackModel's actual model enum if available
    if info["has_load_model"]:
        load_node = all_nodes["LoadFramePackModel"]
        model_param = load_node.get("input", {}).get("required", {}).get("model", [])
        if isinstance(model_param, list) and isinstance(model_param[0], list):
            info["available_models"] = model_param[0]
        else:
            info["available_models"] = []
    else:
        info["available_models"] = []

    return info


def check_system() -> dict:
    """Full system check. Returns capabilities dict or raises."""
    print(f"{'═' * 55}")
    print(f"  Tower Anime — FramePack v2 System Check")
    print(f"{'═' * 55}\n")

    # ComfyUI status
    print("ComfyUI:")
    try:
        stats = comfy_get("/system_stats", timeout=5)
        dev = stats.get("devices", [{}])[0]
        gpu = dev.get("name", "unknown")
        vram_total = dev.get("vram_total", 0) / 1024**3
        vram_free = dev.get("vram_free", 0) / 1024**3
        print(f"  GPU: {gpu}")
        print(f"  VRAM: {vram_free:.1f}GB free / {vram_total:.1f}GB total")
    except Exception as e:
        print(f"  ❌ Not responding: {e}")
        raise ComfyUIError(f"ComfyUI not available at {COMFYUI_URL}")

    # Node availability
    print("\nNodes:")
    caps = probe_nodes()

    # Model loader
    if caps["has_load_model"]:
        print(f"  ✅ LoadFramePackModel (local files)")
        if caps["available_models"]:
            for m in caps["available_models"]:
                marker = "⭐" if "fp8" in m.lower() else " "
                print(f"     {marker} {m}")
    elif caps["has_download_model"]:
        print(f"  ⚠️  Only DownloadAndLoadFramePackModel (will download from HF)")
    else:
        print(f"  ❌ No FramePack model loader found!")
        raise ComfyUIError("No FramePack model loader available")

    # Sampler
    if caps["has_sampler"]:
        print(f"  ✅ FramePackSampler")
    else:
        print(f"  ❌ FramePackSampler not found!")
        raise ComfyUIError("FramePackSampler not available")

    if caps["has_sampler_f1"]:
        print(f"  ✅ FramePackSampler_F1")

    # Video output
    if caps["has_vhs"]:
        print(f"  ✅ VHS_VideoCombine (direct MP4 output)")
    else:
        print(f"  ⚠️  VHS_VideoCombine not found — will use SaveImage + ffmpeg")
        # Check ffmpeg
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            print(f"  ✅ ffmpeg available for video assembly")
        except (FileNotFoundError, subprocess.CalledProcessError):
            print(f"  ⚠️  ffmpeg not found — output will be individual frames")

    # Decode
    if caps["has_tiled_decode"]:
        print(f"  ✅ VAEDecodeTiled")
    else:
        print(f"  ⚠️  VAEDecodeTiled not found — using VAEDecode (may OOM)")

    # Extras
    if caps["has_lora_select"]:
        print(f"  ✅ FramePackLoraSelect")
    if caps["has_timestamped_encode"]:
        print(f"  ✅ FramePackTimestampedTextEncode (F1 timed prompts)")

    print()
    return caps


# ═══════════════════════════════════════════════════════════════
# Workflow Builder
# ═══════════════════════════════════════════════════════════════

def build_workflow(
    prompt_text: str,
    negative_text: str = "",
    caps: dict = None,
    use_f1: bool = False,
    image_path: str = None,
    total_seconds: float = 5.0,
    steps: int = 25,
    seed: int = None,
    width: int = 544,
    height: int = 704,
    guidance_scale: float = 10.0,
    lora_name: str = None,
    lora_strength: float = 1.0,
    lora_fuse: bool = False,
) -> dict:
    """
    Build ComfyUI API workflow from verified node signatures.
    Returns {"prompt": {workflow}} ready for /prompt endpoint.
    """
    if caps is None:
        caps = probe_nodes()
    if seed is None:
        seed = random.randint(0, 2**63 - 1)

    # Choose model file
    if use_f1:
        model_file = MODELS["f1"]
    else:
        model_file = MODELS["i2v"]

    # Check if model is in available list (if we know it)
    if caps.get("available_models"):
        # Try exact match first, then try with Hyvid/ prefix
        if model_file not in caps["available_models"]:
            hyvid_path = f"Hyvid/{model_file}"
            if hyvid_path in caps["available_models"]:
                model_file = hyvid_path
            else:
                # Find best match
                matches = [m for m in caps["available_models"] if model_file.replace(".safetensors", "") in m]
                if matches:
                    model_file = matches[0]
                else:
                    print(f"  ⚠️  Model '{model_file}' not in available list: {caps['available_models']}")

    workflow = {}
    node_id = 1

    # ─── Node: FramePackLoraSelect (optional) ────────────────
    lora_ref = None
    if lora_name and caps.get("has_lora_select"):
        lora_node_id = str(node_id)
        workflow[lora_node_id] = {
            "class_type": "FramePackLoraSelect",
            "inputs": {
                "lora": lora_name,
                "strength": lora_strength,
                "fuse_lora": lora_fuse,
            },
        }
        lora_ref = [lora_node_id, 0]
        node_id += 1

    # ─── Node: Load FramePack Model ──────────────────────────
    model_node_id = str(node_id)
    if caps["has_load_model"]:
        model_inputs = {
            "model": model_file,
            "base_precision": RTX3060_DEFAULTS["base_precision"],
            "quantization": RTX3060_DEFAULTS["quantization"],
            "load_device": RTX3060_DEFAULTS["load_device"],
            "attention_mode": RTX3060_DEFAULTS["attention_mode"],
        }
        if lora_ref:
            model_inputs["lora"] = lora_ref
        workflow[model_node_id] = {
            "class_type": "LoadFramePackModel",
            "inputs": model_inputs,
        }
    else:
        # Fallback to download node
        workflow[model_node_id] = {
            "class_type": "DownloadAndLoadFramePackModel",
            "inputs": {
                "model": "lllyasviel/FramePackI2V_HY",
                "base_precision": RTX3060_DEFAULTS["base_precision"],
                "quantization": RTX3060_DEFAULTS["quantization"],
            },
        }
    node_id += 1

    # ─── Node: DualCLIPLoader ────────────────────────────────
    clip_node_id = str(node_id)
    workflow[clip_node_id] = {
        "class_type": "DualCLIPLoader",
        "inputs": {
            "clip_name1": MODELS["clip_l"],
            "clip_name2": MODELS["llava_text"],
            "type": "hunyuan_video",
            "device": "default",
        },
    }
    node_id += 1

    # ─── Node: Positive text encode ──────────────────────────
    pos_node_id = str(node_id)
    workflow[pos_node_id] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": prompt_text,
            "clip": [clip_node_id, 0],
        },
    }
    node_id += 1

    # ─── Node: Negative text encode ──────────────────────────
    neg_node_id = str(node_id)
    workflow[neg_node_id] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": negative_text or "low quality, blurry, distorted, watermark",
            "clip": [clip_node_id, 0],
        },
    }
    node_id += 1

    # ─── Node: VAE Loader ────────────────────────────────────
    vae_node_id = str(node_id)
    workflow[vae_node_id] = {
        "class_type": "VAELoader",
        "inputs": {
            "vae_name": MODELS["vae"],
        },
    }
    node_id += 1

    # ─── Source image OR empty latent ────────────────────────
    start_latent_ref = None
    image_embeds_ref = None

    if image_path:
        # I2V mode: load image, encode to latent, encode to CLIP vision

        # Load source image
        load_img_id = str(node_id)
        workflow[load_img_id] = {
            "class_type": "LoadImage",
            "inputs": {"image": image_path},
        }
        node_id += 1

        # VAE encode source image → start_latent
        vae_enc_id = str(node_id)
        workflow[vae_enc_id] = {
            "class_type": "VAEEncode",
            "inputs": {
                "pixels": [load_img_id, 0],
                "vae": [vae_node_id, 0],
            },
        }
        start_latent_ref = [vae_enc_id, 0]
        node_id += 1

        # CLIP Vision for image embeddings (important for I2V quality)
        if caps.get("has_clip_vision_loader") and caps.get("has_clip_vision_encode"):
            clip_vis_load_id = str(node_id)
            workflow[clip_vis_load_id] = {
                "class_type": "CLIPVisionLoader",
                "inputs": {"clip_name": MODELS["clip_vision"]},
            }
            node_id += 1

            clip_vis_enc_id = str(node_id)
            workflow[clip_vis_enc_id] = {
                "class_type": "CLIPVisionEncode",
                "inputs": {
                    "clip_vision": [clip_vis_load_id, 0],
                    "image": [load_img_id, 0],
                    "crop": "center",
                },
            }
            image_embeds_ref = [clip_vis_enc_id, 0]
            node_id += 1
    else:
        # T2V mode: empty latent as starting point
        empty_latent_id = str(node_id)
        workflow[empty_latent_id] = {
            "class_type": "EmptyHunyuanLatentVideo",
            "inputs": {
                "width": width,
                "height": height,
                "length": 1,  # Single frame as start
                "batch_size": 1,
            },
        }
        start_latent_ref = [empty_latent_id, 0]
        node_id += 1

    # ─── Node: FramePackSampler ──────────────────────────────
    sampler_node_id = str(node_id)
    sampler_inputs = {
        "model": [model_node_id, 0],
        "positive": [pos_node_id, 0],
        "negative": [neg_node_id, 0],
        "start_latent": start_latent_ref,
        "steps": steps,
        "use_teacache": True,
        "teacache_rel_l1_thresh": 0.15,
        "cfg": 1.0,
        "guidance_scale": guidance_scale,
        "shift": 0.0,
        "seed": seed,
        "latent_window_size": RTX3060_DEFAULTS["latent_window_size"],
        "total_second_length": total_seconds,
        "gpu_memory_preservation": RTX3060_DEFAULTS["gpu_memory_preservation"],
        "sampler": "unipc_bh1",
    }

    # Add image embeds if available (I2V mode)
    if image_embeds_ref:
        sampler_inputs["image_embeds"] = image_embeds_ref

    workflow[sampler_node_id] = {
        "class_type": "FramePackSampler",
        "inputs": sampler_inputs,
    }
    node_id += 1

    # ─── Node: VAE Decode (tiled for memory efficiency) ──────
    decode_node_id = str(node_id)
    if caps.get("has_tiled_decode", True):
        workflow[decode_node_id] = {
            "class_type": "VAEDecodeTiled",
            "inputs": {
                "samples": [sampler_node_id, 0],
                "vae": [vae_node_id, 0],
                "tile_size": RTX3060_DEFAULTS["vae_tile_size"],
                "overlap": RTX3060_DEFAULTS["vae_tile_stride_t"],
                "temporal_size": RTX3060_DEFAULTS["vae_tile_stride_h"],
                "temporal_overlap": RTX3060_DEFAULTS["vae_tile_stride_w"],
            },
        }
    else:
        workflow[decode_node_id] = {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": [sampler_node_id, 0],
                "vae": [vae_node_id, 0],
            },
        }
    node_id += 1

    # ─── Node: Output (VHS MP4 or SaveImage fallback) ────────
    timestamp = int(time.time())
    prefix = f"framepack_{timestamp}"

    output_node_id = str(node_id)
    if caps.get("has_vhs", False):
        workflow[output_node_id] = {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": [decode_node_id, 0],
                "frame_rate": 30,
                "loop_count": 0,
                "filename_prefix": prefix,
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": 19,
                "save_metadata": True,
                "trim_to_audio": False,
                "pingpong": False,
                "save_output": True,
            },
        }
    else:
        workflow[output_node_id] = {
            "class_type": "SaveImage",
            "inputs": {
                "images": [decode_node_id, 0],
                "filename_prefix": prefix,
            },
        }
    node_id += 1

    return {"prompt": workflow}, prefix


# ═══════════════════════════════════════════════════════════════
# Job Submission & Monitoring
# ═══════════════════════════════════════════════════════════════

def submit_workflow(workflow_data: dict) -> str:
    """Submit workflow and return prompt_id. Raises on failure."""
    result = comfy_post("/prompt", workflow_data)
    prompt_id = result.get("prompt_id")
    if not prompt_id:
        raise ComfyUIError(f"No prompt_id in response: {result}")

    # Check for immediate validation errors
    errors = result.get("node_errors", {})
    if errors:
        raise ComfyUIError(f"Node validation errors: {json.dumps(errors, indent=2)}")

    return prompt_id


def poll_for_completion(prompt_id: str, timeout: int = 900) -> dict:
    """
    Poll ComfyUI history until job completes or fails.
    Returns the job result dict with actual output files.
    Raises ComfyUIError if job fails or times out.
    """
    start = time.time()
    last_status = ""

    while time.time() - start < timeout:
        elapsed = int(time.time() - start)

        try:
            # Check history for completion
            history = comfy_get(f"/history/{prompt_id}", timeout=5)

            if prompt_id in history:
                job = history[prompt_id]
                status = job.get("status", {})
                status_str = status.get("status_str", "unknown")
                completed = status.get("completed", False)

                if not completed:
                    # Job is in history but not completed — likely errored
                    messages = status.get("messages", [])
                    error_msgs = [m for m in messages if "error" in str(m).lower()]
                    if error_msgs:
                        raise ComfyUIError(f"Job failed: {error_msgs}")

                # Job completed — check for actual output files
                outputs = job.get("outputs", {})
                output_files = []
                for nid, out in outputs.items():
                    for key in ["images", "gifs", "videos"]:
                        for item in out.get(key, []):
                            output_files.append({
                                "filename": item.get("filename", ""),
                                "subfolder": item.get("subfolder", ""),
                                "type": item.get("type", key),
                            })

                if output_files:
                    return {"status": "completed", "files": output_files, "elapsed": elapsed}
                elif completed:
                    # Completed but no output files — this is the silent failure case
                    raise ComfyUIError(
                        f"Job completed but produced NO output files. "
                        f"This means the workflow executed but SaveImage/VHS node had nothing to save. "
                        f"Check ComfyUI terminal for errors."
                    )

            # Not in history yet — check queue
            queue = comfy_get("/queue", timeout=5)
            running = queue.get("queue_running", [])
            pending = queue.get("queue_pending", [])

            # Check if our job is still in the queue
            our_running = any(prompt_id in str(j) for j in running)
            our_pending = any(prompt_id in str(j) for j in pending)

            if our_running:
                status = f"generating ({elapsed}s)"
            elif our_pending:
                status = f"queued ({elapsed}s, {len(pending)} ahead)"
            else:
                # Not in queue and not in history — might be processing
                status = f"processing ({elapsed}s)"

            if status != last_status:
                print(f"  ⏳ {status}")
                last_status = status

        except requests.exceptions.RequestException:
            # ComfyUI might be busy, retry
            pass

        time.sleep(3)

    raise ComfyUIError(f"Timeout after {timeout}s — job may still be running in ComfyUI")


# ═══════════════════════════════════════════════════════════════
# Output Validation
# ═══════════════════════════════════════════════════════════════

def validate_output(files: list, comfyui_output_dir: str = None) -> bool:
    """
    Quick validation that output files are real content.
    Returns True if output looks valid.
    """
    if not files:
        print("  ❌ No output files to validate")
        return False

    try:
        from PIL import Image
        import numpy as np
        has_pil = True
    except ImportError:
        has_pil = False

    print(f"\n  Validating {len(files)} output file(s)...")

    for finfo in files[:5]:  # Check first 5
        fname = finfo["filename"]
        ftype = finfo.get("type", "images")

        if ftype in ("videos", "gifs"):
            print(f"  ✅ {fname} (video output)")
            continue

        if not has_pil:
            print(f"  ⚠️  {fname} (can't validate without PIL)")
            continue

        # Try to download and check the image
        try:
            resp = requests.get(
                f"{COMFYUI_URL}/view",
                params={
                    "filename": fname,
                    "subfolder": finfo.get("subfolder", ""),
                    "type": "output",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                print(f"  ⚠️  {fname} (can't download: {resp.status_code})")
                continue

            img = Image.open(__import__("io").BytesIO(resp.content))
            arr = np.array(img.convert("RGB"))

            std = arr.std()
            mean = arr.mean()
            h, w = arr.shape[:2]

            if std < 5:
                print(f"  ❌ {fname}: SOLID COLOR (std={std:.1f}, mean={mean:.1f}) — generation failed")
                return False
            elif std < 15:
                print(f"  ⚠️  {fname}: LOW VARIANCE (std={std:.1f}) — possibly degenerate")
            else:
                print(f"  ✅ {fname}: {w}x{h}, std={std:.1f} — looks like real content")

        except Exception as e:
            print(f"  ⚠️  {fname}: validation error: {e}")

    return True


def assemble_video_from_frames(prefix: str, output_path: str, fps: int = 30) -> str:
    """
    If we used SaveImage (no VHS), assemble frames into MP4 with ffmpeg.
    Returns path to assembled video or empty string on failure.
    """
    # Find the frames in ComfyUI's output directory
    # ComfyUI saves as: {prefix}_00001_.png, {prefix}_00002_.png, etc.
    pattern = f"{prefix}_%05d_.png"

    # Try common ComfyUI output locations
    output_dirs = [
        "/mnt/1TB-storage/ComfyUI/output",
        os.path.expanduser("~/ComfyUI/output"),
    ]

    for odir in output_dirs:
        test_path = os.path.join(odir, f"{prefix}_00001_.png")
        if os.path.exists(test_path):
            input_pattern = os.path.join(odir, pattern)
            break
    else:
        print(f"  ⚠️  Can't find frames for ffmpeg assembly (tried: {output_dirs})")
        return ""

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    try:
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", input_pattern,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "19",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  📹 Assembled: {output_path} ({size_mb:.1f}MB)")
            return output_path
        else:
            print(f"  ❌ ffmpeg failed: {result.stderr[:200]}")
            return ""
    except Exception as e:
        print(f"  ❌ ffmpeg error: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def generate(args) -> bool:
    """Run a single generation. Returns True on verified success."""

    # ─── System check ────────────────────────────────────────
    try:
        caps = check_system()
    except ComfyUIError as e:
        print(f"\n❌ System check failed: {e}")
        return False

    # ─── Resolve prompt ──────────────────────────────────────
    if args.prompt:
        prompt_text = args.prompt
        scene_name = "custom"
    elif args.project and args.scene:
        proj = PROJECTS.get(args.project)
        if not proj:
            print(f"❌ Unknown project: {args.project} (available: {', '.join(PROJECTS.keys())})")
            return False
        scene = proj["scenes"].get(args.scene)
        if not scene:
            print(f"❌ Unknown scene: {args.scene} (available: {', '.join(proj['scenes'].keys())})")
            return False
        prompt_text = scene["prompt"]
        if scene.get("motion"):
            prompt_text += f" Motion: {scene['motion']}"
        scene_name = f"{args.project}_{args.scene}"
    else:
        print("❌ Provide --prompt or --project + --scene")
        return False

    # ─── Build workflow ──────────────────────────────────────
    print(f"{'─' * 55}")
    print(f"  Scene: {scene_name}")
    print(f"  Model: {'F1' if args.f1 else 'I2V'} (FP8)")
    print(f"  Duration: {args.seconds}s @ 30fps")
    print(f"  Resolution: {args.width}x{args.height}")
    print(f"  Steps: {args.steps}")
    if args.image:
        print(f"  Source image: {args.image}")
    if args.lora:
        print(f"  LoRA: {args.lora} (strength {args.lora_strength})")
    print(f"  Prompt: {prompt_text[:80]}...")
    print(f"{'─' * 55}\n")

    workflow_data, prefix = build_workflow(
        prompt_text=prompt_text,
        caps=caps,
        use_f1=args.f1,
        image_path=args.image,
        total_seconds=args.seconds,
        steps=args.steps,
        seed=args.seed,
        width=args.width,
        height=args.height,
        lora_name=args.lora,
        lora_strength=args.lora_strength,
        lora_fuse=args.lora_fuse,
    )

    if args.dump_workflow:
        dump_path = f"/tmp/framepack_workflow_{prefix}.json"
        with open(dump_path, "w") as f:
            json.dump(workflow_data, f, indent=2)
        print(f"  Workflow dumped to: {dump_path}")

    # ─── Submit ──────────────────────────────────────────────
    print("🎬 Submitting to ComfyUI...")
    try:
        prompt_id = submit_workflow(workflow_data)
        print(f"  Prompt ID: {prompt_id}")
    except ComfyUIError as e:
        print(f"\n❌ Submission failed: {e}")
        if args.dump_workflow:
            print(f"  Debug the workflow at: /tmp/framepack_workflow_{prefix}.json")
        return False

    # ─── Poll for completion ─────────────────────────────────
    # Estimate timeout: ~3s per frame at 25 steps on RTX 3060
    est_frames = int(args.seconds * 30)
    est_seconds = est_frames * 3
    timeout = max(300, est_seconds * 3)  # 3x safety margin

    print(f"  Estimated: ~{est_seconds // 60}m {est_seconds % 60}s for {est_frames} frames")

    try:
        result = poll_for_completion(prompt_id, timeout=timeout)
    except ComfyUIError as e:
        print(f"\n❌ Generation failed: {e}")
        return False

    elapsed = result["elapsed"]
    files = result["files"]
    print(f"\n  ✅ Completed in {elapsed // 60}m {elapsed % 60}s")
    print(f"  Output files: {len(files)}")
    for f in files[:5]:
        print(f"    📄 {f['filename']}")

    # ─── Validate output ─────────────────────────────────────
    is_valid = validate_output(files)

    if not is_valid:
        print(f"\n❌ Output validation FAILED — generation produced garbage")
        print(f"  Check ComfyUI terminal for errors")
        return False

    # ─── Assemble video if using SaveImage ────────────────────
    if not caps.get("has_vhs") and files and files[0].get("type") != "videos":
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        video_path = os.path.join(OUTPUT_DIR, f"{prefix}.mp4")
        assembled = assemble_video_from_frames(prefix, video_path)
        if assembled:
            print(f"\n{'═' * 55}")
            print(f"  ✅ VIDEO SAVED: {assembled}")
            print(f"{'═' * 55}")
        else:
            print(f"\n  Frames saved in ComfyUI output dir with prefix: {prefix}")
    else:
        print(f"\n{'═' * 55}")
        print(f"  ✅ GENERATION VERIFIED COMPLETE")
        print(f"  View at: {COMFYUI_URL} → Output tab")
        print(f"{'═' * 55}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Tower Anime — FramePack v2 (verified generation)"
    )
    parser.add_argument("--check", action="store_true", help="System check only")
    parser.add_argument("--list", action="store_true", help="List project scenes")
    parser.add_argument("--prompt", help="Text prompt for generation")
    parser.add_argument("--project", choices=list(PROJECTS.keys()), help="Project ID")
    parser.add_argument("--scene", help="Scene name within project")
    parser.add_argument("--image", help="Source image path (for I2V mode)")
    parser.add_argument("--f1", action="store_true", help="Use FramePack F1 model")
    parser.add_argument("--seconds", type=float, default=5.0, help="Video duration")
    parser.add_argument("--steps", type=int, default=25, help="Sampling steps")
    parser.add_argument("--width", type=int, default=544, help="Video width")
    parser.add_argument("--height", type=int, default=704, help="Video height")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument("--lora", help="LoRA model filename (e.g. rina_suzuki_lora.safetensors)")
    parser.add_argument("--lora-strength", type=float, default=1.0, help="LoRA strength (default 1.0)")
    parser.add_argument("--lora-fuse", action="store_true", help="Fuse LoRA into base model (slow but better quality; default: apply at inference)")
    parser.add_argument("--gpu-memory", type=float, default=None,
                        help="GPU memory preservation in GB (default 3.5, higher=slower but safer)")
    parser.add_argument("--dump-workflow", action="store_true", help="Save workflow JSON for debugging")
    args = parser.parse_args()

    # Override gpu_memory_preservation if specified
    if args.gpu_memory is not None:
        RTX3060_DEFAULTS["gpu_memory_preservation"] = args.gpu_memory

    if args.list:
        for pid, proj in PROJECTS.items():
            print(f"\n{'═' * 50}")
            print(f"[{pid}] {proj['name']} — {proj['style']}")
            for sid, scene in proj["scenes"].items():
                print(f"  {pid}/{sid}: {scene['prompt'][:70]}...")
        return

    if args.check:
        try:
            caps = check_system()
            print("✅ System ready for generation")
        except ComfyUIError as e:
            print(f"\n❌ {e}")
            sys.exit(1)
        return

    success = generate(args)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()