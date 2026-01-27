"""
ComfyUI integration service for Tower Anime Production API
Handles low-level ComfyUI API interactions
"""

import os
import logging
import asyncio
import aiohttp
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Configuration - Use domain-aware configuration
from ..core.config import COMFYUI_URL as DEFAULT_COMFYUI_URL
COMFYUI_URL = os.getenv('COMFYUI_URL', DEFAULT_COMFYUI_URL)


class ComfyUIService:
    """Service for ComfyUI API interactions"""

    def __init__(self):
        self.base_url = COMFYUI_URL

    async def submit_workflow(self, workflow: Dict[str, Any]) -> Optional[str]:
        """Submit a workflow to ComfyUI and return the prompt ID"""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"prompt": workflow}
                async with session.post(f"{self.base_url}/prompt", json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get("prompt_id")
                    else:
                        error_text = await response.text()
                        logger.error(f"ComfyUI submission failed: {response.status} - {error_text}")
                        return None
        except Exception as e:
            logger.error(f"ComfyUI connection failed: {e}")
            return None

    async def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status from ComfyUI"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/queue") as response:
                    if response.status == 200:
                        return await response.json()
                    return {"error": f"Failed to get queue status: {response.status}"}
        except Exception as e:
            logger.error(f"Error getting queue status: {e}")
            return {"error": str(e)}

    async def get_history(self, prompt_id: Optional[str] = None) -> Dict[str, Any]:
        """Get workflow history from ComfyUI"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/history"
                if prompt_id:
                    url += f"/{prompt_id}"
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    return {"error": f"Failed to get history: {response.status}"}
        except Exception as e:
            logger.error(f"Error getting history: {e}")
            return {"error": str(e)}

    async def interrupt_processing(self) -> bool:
        """Interrupt current processing in ComfyUI"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/interrupt") as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"Error interrupting processing: {e}")
            return False

    async def get_workflow_progress(self, prompt_id: str) -> Dict[str, Any]:
        """Get progress information for a specific workflow"""
        try:
            queue_status = await self.get_queue_status()

            # Check if prompt is running
            running = queue_status.get("queue_running", [])
            for job in running:
                if prompt_id in str(job):
                    return {
                        "prompt_id": prompt_id,
                        "status": "running",
                        "progress": 0.5,
                        "position": 0
                    }

            # Check if prompt is pending
            pending = queue_status.get("queue_pending", [])
            for i, job in enumerate(pending):
                if prompt_id in str(job):
                    return {
                        "prompt_id": prompt_id,
                        "status": "pending",
                        "progress": 0.0,
                        "position": i + 1
                    }

            # Check if prompt is completed
            history = await self.get_history(prompt_id)
            if prompt_id in history:
                return {
                    "prompt_id": prompt_id,
                    "status": "completed",
                    "progress": 1.0,
                    "position": 0
                }

            return {
                "prompt_id": prompt_id,
                "status": "not_found",
                "progress": 0.0,
                "position": -1
            }

        except Exception as e:
            logger.error(f"Error getting workflow progress: {e}")
            return {
                "prompt_id": prompt_id,
                "status": "error",
                "progress": 0.0,
                "position": -1,
                "error": str(e)
            }

    async def get_models(self) -> List[str]:
        """Get list of available models from ComfyUI"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/object_info") as response:
                    if response.status == 200:
                        object_info = await response.json()
                        checkpoints = object_info.get("CheckpointLoaderSimple", {}).get("input", {}).get("ckpt_name", [])
                        if isinstance(checkpoints, list):
                            return checkpoints
                        return []
                    return []
        except Exception as e:
            logger.error(f"Error getting models: {e}")
            return []

    async def get_loras(self) -> List[str]:
        """Get list of available LoRAs from ComfyUI"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/object_info") as response:
                    if response.status == 200:
                        object_info = await response.json()
                        loras = object_info.get("LoraLoader", {}).get("input", {}).get("lora_name", [])
                        if isinstance(loras, list):
                            return loras
                        return []
                    return []
        except Exception as e:
            logger.error(f"Error getting LoRAs: {e}")
            return []

    async def health_check(self) -> bool:
        """Check if ComfyUI is accessible and healthy"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/system_stats") as response:
                    return response.status == 200
        except Exception:
            return False

    def build_basic_text2img_workflow(
        self,
        prompt: str,
        negative_prompt: str = "worst quality, low quality, blurry",
        checkpoint: str = "realisticVision_v51.safetensors",
        width: int = 512,
        height: int = 768,
        steps: int = 20,
        cfg: float = 7.5,
        seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """Build a basic text2img workflow"""
        import random
        import time

        if seed is None:
            seed = random.randint(0, 1000000)

        return {
            "3": {
                "inputs": {
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "denoise": 1,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0]
                },
                "class_type": "KSampler"
            },
            "4": {
                "inputs": {"ckpt_name": checkpoint},
                "class_type": "CheckpointLoaderSimple"
            },
            "5": {
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1
                },
                "class_type": "EmptyLatentImage"
            },
            "6": {
                "inputs": {
                    "text": f"{prompt}, masterpiece, best quality",
                    "clip": ["4", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "7": {
                "inputs": {
                    "text": negative_prompt,
                    "clip": ["4", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "8": {
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2]
                },
                "class_type": "VAEDecode"
            },
            "9": {
                "inputs": {
                    "filename_prefix": f"anime_image_{int(time.time())}",
                    "images": ["8", 0]
                },
                "class_type": "SaveImage"
            }
        }


# Global service instance
comfyui_service = ComfyUIService()