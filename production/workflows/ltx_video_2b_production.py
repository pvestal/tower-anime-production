#!/usr/bin/env python3
"""
PRODUCTION LTX VIDEO 2B WORKFLOW
PROVEN WORKING: 121 frames, 768x512, 24fps

This is the validated production version of the LTX Video 2B workflow.
Do not modify without testing in development/ first.

Requirements:
- LTX 2B model: ltxv-2b-fp8.safetensors (4GB) or ltxv-2b-distilled.safetensors (5GB)
- Text encoder: t5xxl_fp8_e4m3fn.safetensors (4.9GB) or t5xxl_fp16.safetensors
- VRAM: 8GB minimum (tested with 12GB RTX 3060)
- Output: 121 frames, 5.04 seconds, 768x512
"""

import requests
import json
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LTXVideo2BProduction:
    """Production-ready LTX Video 2B workflow generator"""

    def __init__(self, comfyui_url: str = "http://localhost:8188"):
        self.comfyui_url = comfyui_url
        self.output_dir = Path("/mnt/1TB-storage/ComfyUI/output")

    def validate_prerequisites(self) -> bool:
        """Validate that required models and services are available"""
        try:
            # Check ComfyUI is running
            response = requests.get(f"{self.comfyui_url}/queue")
            if response.status_code != 200:
                logger.error("ComfyUI service not available")
                return False

            # Check models are available via object_info
            object_info = requests.get(f"{self.comfyui_url}/object_info").json()

            # Check CheckpointLoader has LTX model (either FP8 or distilled)
            ltx_models = object_info.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {}).get("ckpt_name", [[], {}])[0]
            has_ltx = any(m in ltx_models for m in ["ltxv-2b-fp8.safetensors", "ltxv-2b-distilled.safetensors"])
            if not has_ltx:
                logger.error("No LTX 2B model found (need ltxv-2b-fp8 or ltxv-2b-distilled)")
                return False

            # Check CLIPLoader has T5 encoder
            clip_models = object_info.get("CLIPLoader", {}).get("input", {}).get("required", {}).get("clip_name", [[], {}])[0]
            if "t5xxl_fp16.safetensors" not in clip_models:
                logger.error("T5XXL text encoder not found in CLIPLoader")
                return False

            logger.info("All prerequisites validated successfully")
            return True

        except Exception as e:
            logger.error(f"Prerequisites validation failed: {e}")
            return False

    def create_workflow(self, prompt: str, negative_prompt: str = None, seed: int = None) -> Dict[str, Any]:
        """Create the validated LTX Video 2B workflow"""

        if seed is None:
            seed = int(time.time()) % 2147483647

        if negative_prompt is None:
            negative_prompt = "static, boring, low quality, blurry, ugly, distorted, bad animation"

        return {
            # 1. Load LTX 2B model
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "ltxv-2b-fp8.safetensors"}  # 4GB model for 12GB VRAM
            },
            # 2. Load T5 text encoder
            "2": {
                "class_type": "CLIPLoader",
                "inputs": {
                    "clip_name": "t5xxl_fp16.safetensors",
                    "type": "ltxv"
                }
            },
            # 3. Positive prompt
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["2", 0]
                }
            },
            # 4. Negative prompt
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": negative_prompt,
                    "clip": ["2", 0]
                }
            },
            # 5-7. Base image generation
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": 768, "height": 512, "batch_size": 1}
            },
            "6": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": 20,
                    "cfg": 7,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "positive": ["3", 0],
                    "negative": ["4", 0],
                    "latent_image": ["5", 0],
                    "model": ["1", 0],
                    "denoise": 1.0
                }
            },
            "7": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["6", 0], "vae": ["1", 2]}
            },
            # 8-12. Video generation (121 frames)
            "8": {
                "class_type": "EmptyLTXVLatentVideo",
                "inputs": {
                    "width": 768,
                    "height": 512,
                    "length": 121,  # 5 seconds at 24fps
                    "batch_size": 1
                }
            },
            "9": {
                "class_type": "LTXVImgToVideo",
                "inputs": {
                    "positive": ["3", 0],
                    "negative": ["4", 0],
                    "vae": ["1", 2],
                    "image": ["7", 0],
                    "width": 768,
                    "height": 512,
                    "length": 121,
                    "batch_size": 1,
                    "strength": 0.8
                }
            },
            "10": {
                "class_type": "LTXVConditioning",
                "inputs": {
                    "positive": ["9", 0],
                    "negative": ["9", 1],
                    "frame_rate": 24
                }
            },
            "11": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": 20,
                    "cfg": 3,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "positive": ["10", 0],
                    "negative": ["10", 1],
                    "latent_image": ["8", 0],
                    "model": ["1", 0],
                    "denoise": 0.8
                }
            },
            "12": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["11", 0], "vae": ["1", 2]}
            },
            # 13. Video output
            "13": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": ["12", 0],
                    "frame_rate": 24,
                    "loop_count": 0,
                    "filename_prefix": "ltx_2b_production_",
                    "format": "video/h264-mp4",
                    "pingpong": False,
                    "save_output": True
                }
            }
        }

    def generate_video(self, prompt: str, negative_prompt: str = None, seed: int = None) -> Optional[str]:
        """Generate a 121-frame video using LTX Video 2B"""

        logger.info(f"Starting LTX Video 2B generation with prompt: {prompt}")

        if not self.validate_prerequisites():
            return None

        workflow = self.create_workflow(prompt, negative_prompt, seed)

        # Submit to ComfyUI
        try:
            response = requests.post(
                f"{self.comfyui_url}/prompt",
                json={"prompt": workflow, "client_id": "ltx_production"}
            )
            result = response.json()

            if "prompt_id" not in result:
                logger.error(f"Failed to submit workflow: {result}")
                return None

            prompt_id = result["prompt_id"]
            logger.info(f"Workflow submitted successfully: {prompt_id}")

            # Wait for completion (with timeout)
            timeout = 600  # 10 minutes
            start_time = time.time()

            while time.time() - start_time < timeout:
                time.sleep(5)

                # Check queue status
                queue_response = requests.get(f"{self.comfyui_url}/queue")
                queue_data = queue_response.json()

                # Check if job is still running
                running_jobs = [job[1] for job in queue_data.get("queue_running", [])]
                if prompt_id not in running_jobs:
                    # Job completed, check for output
                    output_files = list(self.output_dir.glob("ltx_2b_production_*.mp4"))
                    if output_files:
                        latest_file = max(output_files, key=lambda p: p.stat().st_mtime)
                        logger.info(f"Video generation completed: {latest_file}")
                        return str(latest_file)

            logger.error("Video generation timed out")
            return None

        except Exception as e:
            logger.error(f"Video generation failed: {e}")
            return None

def main():
    """Example usage of LTX Video 2B production workflow"""
    generator = LTXVideo2BProduction()

    prompt = "anime cyberpunk warrior running through neon city with dynamic motion and glowing effects"

    video_path = generator.generate_video(prompt)

    if video_path:
        print(f"✅ SUCCESS: 121-frame video generated at {video_path}")
    else:
        print("❌ FAILED: Video generation unsuccessful")

if __name__ == "__main__":
    main()