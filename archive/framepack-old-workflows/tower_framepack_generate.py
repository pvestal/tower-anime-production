#!/usr/bin/env python3
"""
Tower Anime Production — FramePack Video Generation
Grounded in the actual tower-anime-production & tower-lora-studio repos.

This integrates with the existing pipeline at /opt/tower-anime-production/
and uses the real ComfyUI node names from ComfyUI-FramePackWrapper.

Usage:
    # Pre-flight check (no generation)
    python3 tower_framepack_generate.py --check

    # List available scenes
    python3 tower_framepack_generate.py --list

    # Generate a Tokyo Debt Desire scene
    python3 tower_framepack_generate.py --project tdd --scene mei_office

    # Generate with F1 model (better temporal coherence)
    python3 tower_framepack_generate.py --project tdd --scene mei_office --f1

    # Custom prompt
    python3 tower_framepack_generate.py --custom "A woman walks through neon-lit Tokyo streets at night"

    # Image-to-video (animate a character reference image)
    python3 tower_framepack_generate.py --i2v /path/to/mei_reference.png --motion "turns head slowly"
"""

import argparse
import json
import os
import random
import requests
import sys
import time
from pathlib import Path

COMFYUI_URL = "http://127.0.0.1:8188"
OUTPUT_DIR = "/opt/tower-anime-production/output/framepack"

# ═══════════════════════════════════════════════════════════════
# PROJECT SCENE DEFINITIONS — from tower-anime-production repos
# ═══════════════════════════════════════════════════════════════

PROJECTS = {
    "tdd": {
        "name": "Tokyo Debt Desire",
        "style": "modern anime with realistic adult proportions",
        "characters": {
            "mei": {
                "name": "Mei Kobayashi",
                "desc": "beautiful young Japanese woman, long black hair, sharp intelligent eyes",
                "loras_sd15": ["mei_face.safetensors", "mei_working_v1.safetensors"],
                # No HunyuanVideo LoRAs yet — use I2V with reference images
            },
            "kai": {
                "name": "Kai Nakamura",
                "desc": "tall Japanese man, short dark hair, intense gaze, athletic build",
                "loras_sd15": ["kai_nakamura_optimized_v1.safetensors"],
            },
            "rina": {
                "name": "Rina",
                "desc": "young Japanese woman, stylish appearance, confident posture",
                "loras_sd15": ["rina_tdd_real_v2.safetensors"],
            },
            "ryuu": {
                "name": "Ryuu",
                "desc": "Japanese man, rugged appearance, street-smart demeanor",
                "loras_sd15": ["ryuu_working_v1.safetensors"],
            },
        },
        "scenes": {
            "mei_office": {
                "character": "mei",
                "prompt": (
                    "A young Japanese woman with long black hair stands in a modern Tokyo high-rise office, "
                    "wearing a fitted dark business blazer. She gazes out floor-to-ceiling windows at the city skyline. "
                    "Rain streaks down the glass. She slowly turns toward camera. "
                    "Soft warm interior lighting, neon city reflections, cinematic depth of field, photorealistic."
                ),
                "motion": "slow head turn, subtle hair movement from air conditioning, rain on window",
            },
            "kai_rooftop": {
                "character": "kai",
                "prompt": (
                    "A tall athletic Japanese man stands on a Tokyo rooftop at night, wind blowing his jacket. "
                    "Neon signs reflect off wet concrete. He checks his phone, the screen illuminating his face. "
                    "He looks up at the skyline. Cinematic, moody atmosphere, urban night photography style."
                ),
                "motion": "jacket fluttering in wind, phone glow on face, head tilting up",
            },
            "debt_confrontation": {
                "character": "mei",
                "prompt": (
                    "Interior of a dimly lit izakaya bar in Shinjuku. A young Japanese woman with long black hair "
                    "sits across a table from an unseen figure. Tension in her posture. She reaches for a glass of whiskey. "
                    "Warm amber lighting from paper lanterns, cigarette smoke drifting. Film noir atmosphere."
                ),
                "motion": "hand reaching for glass, slight lean forward, smoke drifting",
            },
            "tokyo_night_walk": {
                "character": "mei",
                "prompt": (
                    "A young Japanese woman walks alone through Kabukicho at night. Neon signs in Japanese "
                    "cast colorful reflections on wet pavement. She holds an umbrella, rain falling around her. "
                    "Camera follows from behind then slowly pans to reveal her face. Cinematic tracking shot."
                ),
                "motion": "walking forward, umbrella bobbing slightly, camera pan, rain falling",
            },
        },
    },
    "cgs": {
        "name": "Cyberpunk Goblin Slayer",
        "style": "Arcane (League of Legends) animation style, dark fantasy cyberpunk",
        "characters": {
            "slayer": {
                "name": "Goblin Slayer",
                "desc": "armored figure in futuristic goblin-hunting gear, glowing visor, dark cape",
                "loras_sd15": ["cyberpunk_style_proper.safetensors"],
            },
        },
        "scenes": {
            "neon_alley": {
                "character": "slayer",
                "prompt": (
                    "A dark armored figure with a glowing red visor stalks through a neon-lit cyberpunk alley. "
                    "Rain falls through holographic advertisements. Steam rises from grates. "
                    "The figure draws a plasma blade that crackles with energy. "
                    "Arcane animation style, painterly textures, dramatic rim lighting."
                ),
                "motion": "stalking walk, blade igniting, steam swirling around feet",
            },
        },
    },
    "smg": {
        "name": "Super Mario Galaxy Anime",
        "style": "Illumination Studios 3D movie style",
        "characters": {
            "mario": {"name": "Mario", "desc": "iconic plumber, red cap, blue overalls, mustache"},
            "bowser_jr": {"name": "Bowser Jr.", "desc": "small koopa prince, bandana with teeth design, spiky shell"},
            "rosalina": {"name": "Rosalina", "desc": "tall elegant woman, platinum blonde hair, blue gown, star wand"},
        },
        "scenes": {
            "galaxy_flight": {
                "character": "rosalina",
                "prompt": (
                    "A tall elegant woman with flowing platinum blonde hair floats through a cosmic star field. "
                    "She wears a flowing blue gown that trails behind her like a comet tail. "
                    "Tiny Luma star creatures orbit around her. Galaxies spiral in the background. "
                    "Illumination Studios 3D movie quality, luminous particle effects, magical atmosphere."
                ),
                "motion": "floating gracefully, hair and gown flowing, Lumas orbiting, stars twinkling",
            },
        },
    },
}


def check_comfyui():
    """Verify ComfyUI is running and get node info."""
    try:
        resp = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        stats = resp.json()
        dev = stats.get("devices", [{}])[0]
        vram_free = dev.get("vram_free", 0) / (1024**3)
        vram_total = dev.get("vram_total", 0) / (1024**3)
        gpu_name = dev.get("name", "unknown")
        print(f"  ComfyUI: {gpu_name}")
        print(f"  VRAM: {vram_free:.1f}GB free / {vram_total:.1f}GB total")
        return True
    except Exception as e:
        print(f"  ❌ ComfyUI not responding: {e}")
        return False


def get_framepack_nodes():
    """Get available FramePack node names from ComfyUI."""
    try:
        resp = requests.get(f"{COMFYUI_URL}/object_info", timeout=15)
        nodes = resp.json()
        fp_nodes = {n: nodes[n] for n in nodes if "framepack" in n.lower() or "FramePack" in n}
        return fp_nodes
    except Exception:
        return {}


def discover_workflow(fp_nodes, use_f1=False):
    """
    Figure out which node names to use based on what's actually loaded.
    The wrapper names differ between Kijai's original and the Plus version.
    """
    node_names = set(fp_nodes.keys())

    # Detect which wrapper variant is active
    info = {
        "load_model": None,
        "sampler": None,
        "text_encode": None,
        "has_lora": False,
        "has_timestamp": False,
        "variant": "unknown",
    }

    # Model loader variations
    if "LoadFramePackModel" in node_names:
        info["load_model"] = "LoadFramePackModel"
        info["variant"] = "kijai"
    elif "DownloadAndLoadFramePackModel" in node_names:
        info["load_model"] = "DownloadAndLoadFramePackModel"
        info["variant"] = "plus"

    # F1 sampler
    if use_f1 and "FramePackSampler_F1" in node_names:
        info["sampler"] = "FramePackSampler_F1"
    elif "FramePackSampler" in node_names:
        info["sampler"] = "FramePackSampler"

    # Plus wrapper features
    if "FramePackLoraSelect" in node_names:
        info["has_lora"] = True
        info["variant"] = "plus"
    if "FramePackTimestampedTextEncode" in node_names:
        info["has_timestamp"] = True
        info["text_encode"] = "FramePackTimestampedTextEncode"

    return info


def build_workflow(prompt_text, workflow_info, total_seconds=5.0, seed=None,
                   width=544, height=704, steps=25, use_f1=False, image_path=None):
    """
    Build ComfyUI API workflow using discovered node names.
    """
    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    if use_f1:
        model_file = "FramePack_F1_I2V_HY_20250503_fp8_e4m3fn.safetensors"
    else:
        model_file = "FramePackI2V_HY_fp8_e4m3fn.safetensors"

    load_node = workflow_info.get("load_model", "LoadFramePackModel")
    sampler_node = workflow_info.get("sampler", "FramePackSampler")

    workflow = {}

    # Node 1: Load model
    workflow["1"] = {
        "class_type": load_node,
        "inputs": {
            "model": model_file,
            "base_precision": "fp16",
            "decode_type": "full",
            "samples_type": "latent",
            "load_device": "main_device",
            "quantization": "disabled",
        }
    }

    # Node 2: Load CLIP
    workflow["2"] = {
        "class_type": "DualCLIPLoader",
        "inputs": {
            "clip_name1": "clip_l.safetensors",
            "clip_name2": "llava_llama3_fp16.safetensors",
            "type": "hunyuan_video",
            "device": "default"
        }
    }

    # Node 3: Text encode positive
    workflow["3"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["2", 0],
            "text": prompt_text,
        }
    }

    # Node 4: Empty negative prompt
    workflow["4"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["2", 0],
            "text": "",
        }
    }

    # Node 5: VAE
    workflow["5"] = {
        "class_type": "VAELoader",
        "inputs": {"vae_name": "hunyuan_video_vae_bf16.safetensors"}
    }

    # Node 6: Empty latent for video
    frames = int(total_seconds * 30)
    # Frames must be multiple of 4 for HunyuanVideo
    frames = ((frames + 3) // 4) * 4

    workflow["6"] = {
        "class_type": "EmptyHunyuanLatentVideo",
        "inputs": {
            "length": frames,
            "height": height,
            "width": width,
            "batch_size": 1
        }
    }

    # Node 7: Load image if I2V
    if image_path:
        workflow["7"] = {
            "class_type": "LoadImage",
            "inputs": {"image": image_path}
        }

    # Node 10: Sampler
    sampler_inputs = {
        "model": ["1", 0],
        "positive": ["3", 0],
        "negative": ["4", 0],
        "start_latent": ["6", 0],
        "seed": seed,
        "steps": steps,
        "cfg": 1.0,
        "guidance_scale": 10.0,
        "total_second_length": total_seconds,
        "gpu_memory_preservation": 6,  # Reserve 6GB for RTX 3060
        "sampler": "unipc_bh1",
        "shift": 1.0,
        "latent_window_size": 16,
        "use_teacache": False,
        "teacache_rel_l1_thresh": 0.2,
    }

    if image_path:
        sampler_inputs["image"] = ["7", 0]

    workflow["10"] = {
        "class_type": sampler_node,
        "inputs": sampler_inputs,
    }

    # Node 11: VAE decode
    workflow["11"] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["10", 0],
            "vae": ["5", 0],
        }
    }

    # Node 12: Save images as preview
    workflow["12"] = {
        "class_type": "SaveImage",
        "inputs": {
            "images": ["11", 0],
            "filename_prefix": f"framepack_{int(time.time())}",
        }
    }

    return {"prompt": workflow}


def submit_and_wait(workflow, timeout=900):
    """Submit to ComfyUI and wait for result."""
    print(f"\n🎬 Submitting to ComfyUI...")

    try:
        resp = requests.post(f"{COMFYUI_URL}/prompt", json=workflow, timeout=10)
    except Exception as e:
        print(f"❌ Failed to submit: {e}")
        return None

    if resp.status_code != 200:
        print(f"❌ ComfyUI returned {resp.status_code}")
        try:
            error_data = resp.json()
            if "error" in error_data:
                print(f"   Error: {error_data['error'].get('message', error_data['error'])}")
                if "traceback" in error_data["error"]:
                    print(f"   Details: {error_data['error']['traceback'][-200:]}")
            else:
                print(f"   Response: {error_data}")
        except:
            print(f"   Response: {resp.text[:500]}")
        return None

    data = resp.json()
    prompt_id = data.get("prompt_id")
    if not prompt_id:
        print(f"❌ No prompt_id: {data}")
        return None

    print(f"   Prompt ID: {prompt_id}")

    # Estimate: ~2-4s per frame on RTX 3060
    start = time.time()
    dots = 0
    while time.time() - start < timeout:
        try:
            history = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=5).json()
            if prompt_id in history:
                elapsed = time.time() - start
                print(f"\n   ✅ Done in {elapsed:.0f}s")

                outputs = history[prompt_id].get("outputs", {})
                for nid, out in outputs.items():
                    for key in ["gifs", "videos", "images"]:
                        for item in out.get(key, []):
                            fname = item.get("filename", "")
                            print(f"   📹 {fname}")
                return history[prompt_id]

            # Check for errors
            queue = requests.get(f"{COMFYUI_URL}/queue", timeout=5).json()
            running = len(queue.get("queue_running", []))
            pending = len(queue.get("queue_pending", []))

            elapsed = int(time.time() - start)
            dots = (dots + 1) % 4
            print(f"   ⏳ {elapsed}s — {'.' * (dots+1)}{'  ' * (3-dots)} (queue: {running}r/{pending}p)", end="\r")

        except Exception:
            pass

        time.sleep(5)

    print(f"\n   ⏱️ Timeout after {timeout}s")
    return None


def main():
    parser = argparse.ArgumentParser(description="Tower Anime Production — FramePack Generation")
    parser.add_argument("--check", action="store_true", help="Pre-flight check only")
    parser.add_argument("--list", action="store_true", help="List available project scenes")
    parser.add_argument("--project", choices=["tdd", "cgs", "smg"], help="Project: tdd/cgs/smg")
    parser.add_argument("--scene", help="Scene name from project")
    parser.add_argument("--custom", help="Custom prompt (ignores --project/--scene)")
    parser.add_argument("--i2v", help="Image path for image-to-video")
    parser.add_argument("--motion", default="", help="Motion description for I2V")
    parser.add_argument("--f1", action="store_true", help="Use FramePack F1 model")
    parser.add_argument("--seconds", type=float, default=5.0, help="Duration (default: 5)")
    parser.add_argument("--width", type=int, default=544)
    parser.add_argument("--height", type=int, default=704)
    parser.add_argument("--steps", type=int, default=25)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()

    # ─── List scenes ───
    if args.list:
        for pid, proj in PROJECTS.items():
            print(f"\n{'='*50}")
            print(f"[{pid}] {proj['name']}")
            print(f"    Style: {proj['style']}")
            chars = ", ".join(f"{k} ({v['name']})" for k, v in proj["characters"].items())
            print(f"    Characters: {chars}")
            for sid, scene in proj["scenes"].items():
                print(f"    Scene '{sid}': {scene['prompt'][:80]}...")
        return

    # ─── Pre-flight ───
    print("═" * 50)
    print("  Tower Anime — FramePack Generation")
    print("═" * 50)
    print()

    print("ComfyUI:")
    if not check_comfyui():
        sys.exit(1)

    print("\nFramePack nodes:")
    fp_nodes = get_framepack_nodes()
    if not fp_nodes:
        print("  ❌ No FramePack nodes found!")
        print("  Run: bash framepack_preflight.sh")
        print("  Then restart ComfyUI")
        sys.exit(1)

    for name in sorted(fp_nodes.keys()):
        print(f"  • {name}")

    wf_info = discover_workflow(fp_nodes, use_f1=args.f1)
    print(f"\n  Wrapper variant: {wf_info['variant']}")
    print(f"  Load model node: {wf_info['load_model']}")
    print(f"  Sampler node: {wf_info['sampler']}")
    print(f"  LoRA support: {wf_info['has_lora']}")
    print(f"  Timestamped prompts: {wf_info['has_timestamp']}")

    if args.check:
        if wf_info["load_model"] and wf_info["sampler"]:
            print(f"\n✅ Ready to generate!")
        else:
            print(f"\n❌ Missing critical nodes — check FramePack wrapper installation")
        return

    # ─── Resolve prompt ───
    if args.custom:
        prompt_text = args.custom
        scene_name = "custom"
    elif args.i2v:
        if not os.path.exists(args.i2v):
            print(f"❌ Image not found: {args.i2v}")
            sys.exit(1)
        prompt_text = args.motion or "gentle natural movement, cinematic"
        scene_name = f"i2v_{Path(args.i2v).stem}"
    elif args.project and args.scene:
        proj = PROJECTS.get(args.project)
        if not proj:
            print(f"❌ Unknown project: {args.project}")
            sys.exit(1)
        scene = proj["scenes"].get(args.scene)
        if not scene:
            print(f"❌ Unknown scene: {args.scene}")
            print(f"   Available: {', '.join(proj['scenes'].keys())}")
            sys.exit(1)
        prompt_text = scene["prompt"]
        if scene.get("motion"):
            prompt_text += f" Motion: {scene['motion']}"
        scene_name = f"{args.project}_{args.scene}"
    else:
        parser.print_help()
        print("\n  Example: python3 tower_framepack_generate.py --project tdd --scene mei_office")
        return

    model_label = "F1" if args.f1 else "I2V"
    est_frames = int(args.seconds * 30)
    est_minutes = est_frames * 3 / 60  # ~3s/frame on RTX 3060

    print(f"\n{'─'*50}")
    print(f"  Scene: {scene_name}")
    print(f"  Model: FramePack {model_label} (FP8)")
    print(f"  Duration: {args.seconds}s @ 30fps = {est_frames} frames")
    print(f"  Resolution: {args.width}x{args.height}")
    print(f"  Est. time: ~{est_minutes:.0f} minutes")
    print(f"  Prompt: {prompt_text[:100]}...")
    print(f"{'─'*50}")

    # Build and submit
    workflow = build_workflow(
        prompt_text=prompt_text,
        workflow_info=wf_info,
        total_seconds=args.seconds,
        seed=args.seed,
        width=args.width,
        height=args.height,
        steps=args.steps,
        use_f1=args.f1,
        image_path=args.i2v,
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    result = submit_and_wait(workflow, timeout=max(600, int(est_minutes * 60 * 2)))

    if result:
        print(f"\n{'═'*50}")
        print(f"  ✅ Generation complete!")
        print(f"  Check: {COMFYUI_URL} → Output tab")
        print(f"{'═'*50}")
    else:
        print(f"\n  Generation may still be running in ComfyUI.")
        print(f"  Check: {COMFYUI_URL}")


if __name__ == "__main__":
    main()