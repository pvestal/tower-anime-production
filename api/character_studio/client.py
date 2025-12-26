"""
character_studio/client.py
Low-level ComfyUI API client for character generation workflows
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional

import httpx

logger = logging.getLogger(__name__)


class ComfyUIClient:
    """
    ComfyUI HTTP API client

    Handles workflow submission and status polling
    Does NOT contain business logic
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8188"):
        self.base_url = base_url
        self.timeout = httpx.Timeout(30.0, connect=10.0)

    async def build_character_workflow(
        self,
        prompt: str,
        negative_prompt: str,
        checkpoint: str = "AOM3A1B.safetensors",
        loras: Optional[list] = None,
        sampler: str = "euler",
        scheduler: str = "normal",
        width: int = 512,
        height: int = 768,
        steps: int = 20,
        cfg_scale: float = 7.0,
        seed: int = -1,
        use_controlnet: bool = False,
        controlnet_model: Optional[str] = None,
        pose_reference: Optional[str] = None,
        filename_prefix: str = "character"
    ) -> Dict[str, Any]:
        """
        Build ComfyUI workflow JSON for character generation

        Returns workflow dict ready for submission
        """

        # Generate seed if not provided
        if seed < 0:
            seed = int(time.time() * 1000) % 2147483647

        # Base workflow nodes
        workflow = {
            # Checkpoint loader
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": checkpoint}
            },

            # Empty latent image
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1
                }
            },

            # VAE Decode
            "6": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["4", 0],
                    "vae": ["1", 2]
                }
            },

            # Save Image
            "7": {
                "class_type": "SaveImage",
                "inputs": {
                    "images": ["6", 0],
                    "filename_prefix": filename_prefix
                }
            }
        }

        # Track current model and clip for chaining
        current_model = ["1", 0]
        current_clip = ["1", 1]

        # Chain LoRA loaders if provided
        if loras:
            for idx, lora in enumerate(loras):
                lora_node_id = f"lora_{idx}"
                workflow[lora_node_id] = {
                    "class_type": "LoraLoader",
                    "inputs": {
                        "lora_name": lora.get("name"),
                        "strength_model": lora.get("strength_model", 1.0),
                        "strength_clip": lora.get("strength_clip", 1.0),
                        "model": current_model,
                        "clip": current_clip
                    }
                }
                # Chain to next
                current_model = [lora_node_id, 0]
                current_clip = [lora_node_id, 1]

        # CLIP text encode nodes (use potentially LoRA-modified clip)
        workflow["2"] = {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt,
                "clip": current_clip
            }
        }

        workflow["3"] = {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative_prompt,
                "clip": current_clip
            }
        }

        if use_controlnet and controlnet_model and pose_reference:
            # Add ControlNet nodes
            workflow["8"] = {
                "class_type": "ControlNetLoader",
                "inputs": {
                    "control_net_name": f"{controlnet_model}.pth"
                }
            }

            workflow["9"] = {
                "class_type": "LoadImage",
                "inputs": {
                    "image": pose_reference
                }
            }

            workflow["10"] = {
                "class_type": "ControlNetApply",
                "inputs": {
                    "conditioning": ["2", 0],
                    "control_net": ["8", 0],
                    "image": ["9", 0],
                    "strength": 0.8
                }
            }

            # KSampler with ControlNet
            workflow["4"] = {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg_scale,
                    "sampler_name": sampler,
                    "scheduler": scheduler,
                    "denoise": 1.0,
                    "model": current_model,  # Use LoRA-modified model
                    "positive": ["10", 0],  # ControlNet conditioned
                    "negative": ["3", 0],
                    "latent_image": ["5", 0]
                }
            }
        else:
            # KSampler without ControlNet
            workflow["4"] = {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg_scale,
                    "sampler_name": sampler,
                    "scheduler": scheduler,
                    "denoise": 1.0,
                    "model": current_model,  # Use LoRA-modified model
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["5", 0]
                }
            }

        return workflow

    async def submit_workflow(self, workflow: Dict[str, Any]) -> str:
        """
        Submit workflow to ComfyUI and return prompt_id

        Raises:
            httpx.HTTPError: If submission fails
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow}
            )
            response.raise_for_status()
            data = response.json()

            prompt_id = data.get("prompt_id")
            if not prompt_id:
                raise ValueError(f"No prompt_id in ComfyUI response: {data}")

            logger.info(f"Submitted workflow to ComfyUI: {prompt_id}")
            return prompt_id

    async def get_history(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """
        Get generation history for a prompt_id

        Returns None if not found, dict if found
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/history/{prompt_id}"
                )

                if response.status_code == 200:
                    data = response.json()
                    if prompt_id in data:
                        return data[prompt_id]

                return None

            except httpx.HTTPError as e:
                logger.error(f"Failed to get history for {prompt_id}: {e}")
                return None

    async def poll_until_complete(
        self,
        prompt_id: str,
        timeout: int = 300,
        poll_interval: float = 2.0
    ) -> Optional[str]:
        """
        Poll ComfyUI until generation completes

        Returns:
            Output filename if successful, None if timeout/failure
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            history = await self.get_history(prompt_id)

            if history:
                # Check if has outputs
                outputs = history.get("outputs", {})

                for node_id, node_output in outputs.items():
                    # Check for images
                    if "images" in node_output:
                        images = node_output["images"]
                        if images and len(images) > 0:
                            filename = images[0].get("filename")
                            if filename:
                                logger.info(f"Generation complete: {filename}")
                                return filename

            # Not complete yet, wait
            await asyncio.sleep(poll_interval)

        logger.error(f"Timeout waiting for {prompt_id} after {timeout}s")
        return None

    async def check_health(self) -> bool:
        """Check if ComfyUI is accessible"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/system_stats")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"ComfyUI health check failed: {e}")
            return False

    async def get_available_checkpoints(self) -> list:
        """Get list of available checkpoint models"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/object_info")
                if response.status_code == 200:
                    data = response.json()
                    checkpoint_info = data.get("CheckpointLoaderSimple", {})
                    inputs = checkpoint_info.get("input", {})
                    required = inputs.get("required", {})
                    ckpt_list = required.get("ckpt_name", [[]])[0]
                    return ckpt_list if isinstance(ckpt_list, list) else []
        except Exception as e:
            logger.error(f"Failed to get checkpoint list: {e}")
            return []
