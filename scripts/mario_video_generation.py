#!/usr/bin/env python3
"""
Mario Video Generation with LoRA and LTX-2B
Uses trained Mario LoRA for text-to-video generation
"""

import requests
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional

COMFYUI_URL = "http://localhost:8188"
MARIO_LORA_PATH = "/mnt/1TB-storage/models/loras/mario_lora.safetensors"

def create_mario_ltx_video_workflow(
    prompt: str,
    duration_seconds: int = 3,
    width: int = 768,
    height: int = 512,
    guidance_scale: float = 4.0,
    lora_strength: float = 0.8
) -> Dict[str, Any]:
    """Create LTX-2B video workflow with Mario LoRA"""

    # Generate unique filename
    timestamp = int(time.time())
    filename_prefix = f"mario_video_{timestamp}"
    frame_count = int(duration_seconds * 25)  # 25 FPS

    # Ensure dimensions and frame count are valid for LTX-2B
    width = ((width + 63) // 64) * 64  # Round up to nearest 64
    height = ((height + 63) // 64) * 64  # Round up to nearest 64
    frame_count = ((frame_count - 1) // 8) * 8 + 1  # Must be divisible by 8 + 1

    workflow = {
        # Prompt Input
        "1": {
            "class_type": "PrimitiveStringMultiline",
            "inputs": {
                "value": prompt
            },
            "properties": {},
            "widgets_values": [prompt]
        },

        # Text Encoder
        "2": {
            "class_type": "LTXVGemmaCLIPModelLoader",
            "inputs": {
                "gemma_path": "gemma_3_12B_it.safetensors",
                "ltxv_path": "ltxv-2b-fp8.safetensors",
                "max_length": 1024
            },
            "properties": {},
            "widgets_values": [
                "gemma_3_12B_it.safetensors",
                "ltxv-2b-fp8.safetensors",
                1024
            ]
        },

        # Prompt Enhancement
        "3": {
            "class_type": "LTXVGemmaEnhancePrompt",
            "inputs": {
                "clip": ["2", 0],
                "prompt": ["1", 0],
                "bypass_i2v": False,
                "system_prompt": "",
                "max_tokens": 512
            },
            "properties": {},
            "widgets_values": [
                "",  # system prompt (empty uses default)
                "You are a Creative Assistant. Given a user's raw input prompt describing a scene or concept, expand it into a detailed video generation prompt with specific visuals and integrated audio to guide a text-to-video model.",  # custom system prompt
                512,
                True,
                42,
                "randomize"
            ]
        },

        # Text Encoding
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": ["3", 0],
                "clip": ["2", 0]
            },
            "properties": {},
            "widgets_values": [""]
        },

        # Frame Rate
        "5": {
            "class_type": "PrimitiveFloat",
            "inputs": {
                "value": 25.0
            },
            "properties": {},
            "widgets_values": [25.0]
        },

        # Length
        "6": {
            "class_type": "PrimitiveInt",
            "inputs": {},
            "properties": {},
            "widgets_values": [frame_count, "fixed"]
        },

        # LTX Conditioning
        "7": {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": ["4", 0],
                "negative": ["4", 0],  # Using same for both positive and negative
                "frame_rate": ["5", 0]
            },
            "properties": {},
            "widgets_values": [25]
        },

        # Empty Image for dimensions
        "8": {
            "class_type": "EmptyImage",
            "inputs": {},
            "properties": {},
            "widgets_values": [width, height, 1, 0]
        },

        # Main Model Loader
        "9": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": "ltxv-2b-fp8.safetensors"
            },
            "properties": {},
            "widgets_values": ["ltxv-2b-fp8.safetensors"]
        },

        # Mario LoRA Loader
        "10": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["9", 0],
                "lora_name": "mario_lora.safetensors",
                "strength_model": lora_strength
            },
            "properties": {},
            "widgets_values": [
                "mario_lora.safetensors",
                lora_strength
            ]
        },

        # Audio VAE Loader
        "11": {
            "class_type": "LTXVAudioVAELoader",
            "inputs": {
                "ckpt_name": "ltxv-2b-fp8.safetensors"
            },
            "properties": {},
            "widgets_values": ["ltxv-2b-fp8.safetensors"]
        },

        # Empty Video Latent
        "12": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": width,
                "height": height,
                "length": frame_count,
                "batch_size": 1
            },
            "properties": {},
            "widgets_values": [width, height, frame_count, 1]
        },

        # Empty Audio Latent
        "13": {
            "class_type": "LTXVEmptyLatentAudio",
            "inputs": {
                "audio_vae": ["11", 0],
                "frames_number": frame_count,
                "frame_rate": 25,
                "batch_size": 1
            },
            "properties": {},
            "widgets_values": [frame_count, 25, 1]
        },

        # Combine Audio/Video Latents
        "14": {
            "class_type": "LTXVConcatAVLatent",
            "inputs": {
                "video_latent": ["12", 0],
                "audio_latent": ["13", 0]
            },
            "properties": {},
            "widgets_values": []
        },

        # Sampler
        "15": {
            "class_type": "KSampler",
            "inputs": {
                "seed": int(time.time()) % (2**32),
                "steps": 30,
                "cfg": guidance_scale,
                "sampler_name": "euler",
                "scheduler": "normal",
                "model": ["10", 0],
                "positive": ["7", 0],
                "negative": ["7", 1],
                "latent_image": ["14", 0],
                "denoise": 1.0
            },
            "properties": {},
            "widgets_values": []
        },

        # Separate AV Latent
        "16": {
            "class_type": "LTXVSeparateAVLatent",
            "inputs": {
                "av_latent": ["15", 0]
            },
            "properties": {},
            "widgets_values": []
        },

        # Video VAE Decode
        "17": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["16", 0],
                "vae": ["9", 2]
            },
            "properties": {},
            "widgets_values": []
        },

        # Audio VAE Decode
        "18": {
            "class_type": "LTXVAudioVAEDecode",
            "inputs": {
                "samples": ["16", 1],
                "audio_vae": ["11", 0]
            },
            "properties": {},
            "widgets_values": []
        },

        # Create Video
        "19": {
            "class_type": "CreateVideo",
            "inputs": {
                "images": ["17", 0],
                "audio": ["18", 0],
                "fps": ["5", 0]
            },
            "properties": {},
            "widgets_values": [25]
        },

        # Save Video
        "20": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["19", 0],
                "filename_prefix": filename_prefix,
                "codec": "auto",
                "format": "auto"
            },
            "properties": {},
            "widgets_values": [filename_prefix, "auto", "auto"]
        }
    }

    return workflow

def generate_mario_video(
    prompt: str,
    duration: int = 3,
    width: int = 768,
    height: int = 512,
    timeout: int = 300
) -> Dict[str, Any]:
    """Generate Mario video using LTX-2B with LoRA"""

    print(f"🎬 Generating Mario video...")
    print(f"   Prompt: {prompt}")
    print(f"   Duration: {duration}s at {width}x{height}")

    # Check if Mario LoRA exists
    if not Path(MARIO_LORA_PATH).exists():
        raise FileNotFoundError(f"Mario LoRA not found: {MARIO_LORA_PATH}")

    # Build workflow
    try:
        workflow = create_mario_ltx_video_workflow(
            prompt=prompt,
            duration_seconds=duration,
            width=width,
            height=height
        )
        print("   ✅ Workflow created")
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to build workflow: {e}",
            "prompt": prompt
        }

    # Submit to ComfyUI
    try:
        response = requests.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow},
            timeout=30
        )

        if response.status_code != 200:
            return {
                "status": "error",
                "error": f"ComfyUI error: {response.status_code} - {response.text}",
                "prompt": prompt
            }

        result = response.json()
        prompt_id = result["prompt_id"]
        print(f"   ✅ Queued: {prompt_id}")

    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "error": f"Failed to connect to ComfyUI: {e}",
            "prompt": prompt
        }

    # Wait for completion
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            history_response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
            history = history_response.json()

            if prompt_id in history:
                prompt_history = history[prompt_id]

                # Check if generation is complete (now using node 20 for SaveVideo)
                if "outputs" in prompt_history and "20" in prompt_history["outputs"]:
                    outputs = prompt_history["outputs"]["20"]

                    if "videos" in outputs:
                        videos = outputs.get("videos", [])
                        print(f"   ✅ Video generated: {videos}")

                        # Find generated video files
                        output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
                        generated_files = []

                        for video_info in videos:
                            if "filename" in video_info:
                                video_path = output_dir / video_info["filename"]
                                if video_path.exists():
                                    generated_files.append(str(video_path))

                        return {
                            "status": "success",
                            "prompt": prompt,
                            "prompt_id": prompt_id,
                            "generated_videos": generated_files,
                            "generation_time": time.time() - start_time,
                            "duration": duration,
                            "resolution": f"{width}x{height}",
                            "workflow": workflow
                        }

                # Check for errors
                if "status" in prompt_history and prompt_history["status"].get("completed", False):
                    if not prompt_history.get("outputs"):
                        return {
                            "status": "error",
                            "error": "Generation completed but no outputs found",
                            "prompt": prompt,
                            "prompt_id": prompt_id
                        }

        except requests.exceptions.RequestException as e:
            print(f"   ⚠️ Status check error: {e}")

        time.sleep(5)
        elapsed = time.time() - start_time
        print(f"   ⏳ Generating... {elapsed:.0f}s")

    return {
        "status": "timeout",
        "error": f"Generation timed out after {timeout} seconds",
        "prompt": prompt,
        "prompt_id": prompt_id
    }

def create_multiple_mario_videos(prompts: list) -> Dict[str, Any]:
    """Generate multiple Mario videos with different prompts"""

    results = []
    for i, prompt in enumerate(prompts):
        print(f"\n--- Mario Video {i+1}/{len(prompts)} ---")
        result = generate_mario_video(prompt, duration=3)
        results.append(result)

        # Wait between generations
        if i < len(prompts) - 1:
            print("   ⏸️ Waiting 30 seconds before next video...")
            time.sleep(30)

    return {
        "total_videos": len(prompts),
        "results": results,
        "success_count": sum(1 for r in results if r["status"] == "success"),
        "error_count": sum(1 for r in results if r["status"] == "error")
    }

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python mario_video_generation.py <prompt>")
        print("  python mario_video_generation.py 'mario jumping in super mario world'")
        sys.exit(1)

    prompt = " ".join(sys.argv[1:])

    print(f"🎮 Mario Video Generation with LTX-2B")
    print(f"Prompt: {prompt}")
    print()

    result = generate_mario_video(prompt, duration=3)
    print(json.dumps(result, indent=2))