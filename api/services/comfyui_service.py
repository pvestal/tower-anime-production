"""ComfyUI Integration Service"""

import json
import logging
import time
import uuid
from typing import Dict, Optional
import httpx
from pathlib import Path

logger = logging.getLogger(__name__)

COMFYUI_URL = "http://localhost:8188"


async def submit_to_comfyui(prompt: str, job_id: str, job_type: str = "image") -> bool:
    """Submit job to ComfyUI for processing"""
    try:
        # Create appropriate workflow based on job type
        if job_type == "video":
            from .svd_video_workflow import create_optimal_video_workflow

            # Use Echo Brain to intelligently select the model
            try:
                from .echo_model_selector import EchoModelSelector
                selector = EchoModelSelector()

                # Extract character name if present (simple extraction)
                character_name = None
                if "Kai Nakamura" in prompt or "kai_nakamura" in prompt.lower():
                    character_name = "Kai Nakamura"

                # Get Echo's decision (in shadow mode initially)
                chosen_model, decision_metadata = selector.select_model(prompt, character_name)

                # Log Echo's decision for analysis
                logger.info(f"Echo Model Decision: {decision_metadata.get('model')} "
                          f"(confidence: {decision_metadata.get('confidence', 0):.2f}, "
                          f"shadow_mode: {selector.shadow_mode})")

                # Use Echo's choice if not in shadow mode, otherwise fallback
                prefer_method = chosen_model

            except Exception as e:
                logger.warning(f"Echo selector failed, using fallback: {e}")
                prefer_method = "svd"

            workflow, method_used = await create_optimal_video_workflow(
                prompt=prompt,
                frames=16,
                fps=8,
                width=512,
                height=512,
                prefer_method=prefer_method
            )
            logger.info(f"Using video generation method: {method_used}")

            # Set output filename based on method
            if "VHS_VideoCombine" in str(workflow):
                # Find the VHS_VideoCombine node and update filename
                for node_id, node in workflow.items():
                    if node.get("class_type") == "VHS_VideoCombine":
                        node["inputs"]["filename_prefix"] = f"{job_id}_video"
                        break
        else:
            # Use existing image workflow
            workflow = create_workflow(prompt)
            output_filename = f"{job_id}_00001"
            workflow["9"]["inputs"]["filename_prefix"] = output_filename

        async with httpx.AsyncClient(timeout=60) as client:  # Increased timeout for video
            # Submit prompt
            response = await client.post(
                f"{COMFYUI_URL}/prompt",
                json={
                    "prompt": workflow,
                    "client_id": job_id
                }
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(f"ComfyUI job submitted ({job_type}): {result}")
                return {
                    "success": True,
                    "prompt_id": result.get("prompt_id"),
                    "job_type": job_type
                }
            else:
                logger.error(f"ComfyUI submission failed: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}"
                }

    except Exception as e:
        logger.error(f"Failed to submit to ComfyUI: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def create_workflow(prompt: str) -> Dict:
    """Create ComfyUI workflow from prompt"""
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 42,
                "steps": 15,
                "cfg": 7,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0]
            }
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": "animagine-xl-3.1.safetensors"
            }
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": 832,
                "height": 1216,
                "batch_size": 1
            }
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": f"masterpiece, best quality, {prompt}",
                "clip": ["4", 1]
            }
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "worst quality, low quality, normal quality, lowres, bad anatomy",
                "clip": ["4", 1]
            }
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2]
            }
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["8", 0],
                "filename_prefix": "output"
            }
        }
    }


async def get_comfyui_status() -> Dict:
    """Get ComfyUI queue status"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{COMFYUI_URL}/queue")
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Failed to get ComfyUI status: {e}")

    return {"queue_running": [], "queue_pending": []}