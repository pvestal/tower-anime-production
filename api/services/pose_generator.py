"""
Pose Generation Service for Character Animation
Handles multi-angle turnarounds, NSFW poses, and ControlNet integration
"""
import asyncio
import httpx
import json
import os
from typing import Dict, List, Optional, Literal
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

PoseType = Literal["turnaround", "expressions", "action", "intimate", "nsfw_suggestive", "nsfw_explicit"]

class PoseGenerator:
    """Generates character pose sheets using ControlNet and IPAdapter"""

    def __init__(self, comfyui_url: str = "http://127.0.0.1:8188"):
        self.comfyui_url = comfyui_url
        self.pose_library_path = Path("/mnt/1TB-storage/poses")
        self.nsfw_pose_path = self.pose_library_path / "nsfw"
        self._ensure_directories()

    def _ensure_directories(self):
        """Ensure pose directories exist"""
        self.pose_library_path.mkdir(exist_ok=True, parents=True)
        self.nsfw_pose_path.mkdir(exist_ok=True, parents=True)

    def get_pose_references(self, pose_type: PoseType) -> List[Dict]:
        """
        Get pose reference configurations based on type.
        Returns list of pose definitions with OpenPose data.
        """
        pose_definitions = {
            "turnaround": [
                {"angle": "front", "description": "facing forward, neutral pose"},
                {"angle": "front_left_45", "description": "3/4 view left"},
                {"angle": "left_profile", "description": "left side profile"},
                {"angle": "back_left_45", "description": "3/4 back view left"},
                {"angle": "back", "description": "back view"},
                {"angle": "back_right_45", "description": "3/4 back view right"},
                {"angle": "right_profile", "description": "right side profile"},
                {"angle": "front_right_45", "description": "3/4 view right"},
            ],
            "expressions": [
                {"expression": "neutral", "description": "neutral expression"},
                {"expression": "happy", "description": "smiling, joyful"},
                {"expression": "sad", "description": "sad, melancholic"},
                {"expression": "angry", "description": "angry, fierce"},
                {"expression": "surprised", "description": "shocked, surprised"},
                {"expression": "flirty", "description": "winking, playful"},
            ],
            "action": [
                {"pose": "standing", "description": "standing idle"},
                {"pose": "walking", "description": "mid-walk cycle"},
                {"pose": "running", "description": "running pose"},
                {"pose": "sitting", "description": "sitting on chair"},
                {"pose": "fighting", "description": "combat stance"},
            ],
            "intimate": [
                {"pose": "leaning", "description": "leaning against wall"},
                {"pose": "reclining", "description": "reclining on couch"},
                {"pose": "stretching", "description": "stretching arms up"},
                {"pose": "looking_back", "description": "looking over shoulder"},
            ],
            "nsfw_suggestive": [
                {"pose": "bedroom_eyes", "description": "sultry expression, suggestive"},
                {"pose": "pin_up", "description": "classic pin-up pose"},
                {"pose": "bath_towel", "description": "wrapped in towel, post-bath"},
                {"pose": "lingerie", "description": "lingerie model pose"},
            ],
            "nsfw_explicit": [
                # These would contain more explicit pose definitions
                # Keeping descriptions clinical/technical for safety
                {"pose": "artistic_nude", "description": "artistic nude, tasteful"},
                {"pose": "intimate_couple", "description": "couple pose, intimate"},
            ]
        }

        return pose_definitions.get(pose_type, [])

    async def generate_character_sheet(
        self,
        character_id: int,
        character_image_path: str,
        pose_type: PoseType = "turnaround",
        preserve_clothing: bool = True,
        quality_preset: str = "high",
        nsfw_consent: bool = False
    ) -> Dict:
        """
        Generate a complete character pose sheet.

        Args:
            character_id: Database character ID
            character_image_path: Path to character reference image
            pose_type: Type of poses to generate
            preserve_clothing: Whether to maintain original clothing
            quality_preset: Quality level (draft/standard/high)
            nsfw_consent: Explicit consent required for NSFW content

        Returns:
            Dictionary with pose sheet metadata and image paths
        """
        # Safety check for NSFW content
        if pose_type in ["nsfw_suggestive", "nsfw_explicit"] and not nsfw_consent:
            raise ValueError("NSFW content requires explicit consent flag")

        pose_refs = self.get_pose_references(pose_type)

        logger.info(f"Generating {pose_type} pose sheet with {len(pose_refs)} poses")

        generated_poses = []
        session_id = f"pose_{character_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        async with httpx.AsyncClient(timeout=120.0) as client:
            for i, pose_ref in enumerate(pose_refs, 1):
                logger.info(f"Generating pose {i}/{len(pose_refs)}: {pose_ref}")

                try:
                    # Build workflow based on pose type
                    workflow = await self._build_pose_workflow(
                        character_image_path=character_image_path,
                        pose_definition=pose_ref,
                        pose_type=pose_type,
                        preserve_clothing=preserve_clothing,
                        quality_preset=quality_preset
                    )

                    # Submit to ComfyUI
                    response = await client.post(
                        f"{self.comfyui_url}/prompt",
                        json={"prompt": workflow, "client_id": session_id}
                    )

                    if response.status_code == 200:
                        result = response.json()
                        prompt_id = result["prompt_id"]

                        # Wait for completion (simplified - in production use websocket)
                        output_path = await self._wait_for_result(client, prompt_id, session_id)

                        generated_poses.append({
                            "pose_ref": pose_ref,
                            "output_path": output_path,
                            "prompt_id": prompt_id
                        })

                        logger.info(f"  ✓ Generated: {output_path}")

                    else:
                        logger.error(f"  ❌ ComfyUI error: {response.status_code}")

                    # Rate limiting between poses
                    if i < len(pose_refs):
                        await asyncio.sleep(5)

                except Exception as e:
                    logger.error(f"  ❌ Pose generation failed: {e}")
                    continue

        # Save pose sheet metadata
        pose_sheet = {
            "character_id": character_id,
            "pose_type": pose_type,
            "pose_count": len(generated_poses),
            "poses": generated_poses,
            "session_id": session_id,
            "created_at": datetime.utcnow().isoformat(),
            "nsfw": pose_type in ["nsfw_suggestive", "nsfw_explicit"]
        }

        # Save to tracking file
        self._save_pose_sheet(pose_sheet)

        return pose_sheet

    async def _build_pose_workflow(
        self,
        character_image_path: str,
        pose_definition: Dict,
        pose_type: str,
        preserve_clothing: bool,
        quality_preset: str
    ) -> Dict:
        """
        Build ComfyUI workflow for pose generation.
        Uses ControlNet OpenPose + IPAdapter for consistency.
        """

        # Quality settings based on preset
        quality_settings = {
            "draft": {"steps": 20, "cfg": 7, "denoise": 0.8},
            "standard": {"steps": 30, "cfg": 8, "denoise": 0.75},
            "high": {"steps": 40, "cfg": 8.5, "denoise": 0.7}
        }

        settings = quality_settings.get(quality_preset, quality_settings["standard"])

        # Build appropriate prompt based on pose type
        if pose_type == "turnaround":
            angle = pose_definition.get("angle", "front")
            prompt = f"character turnaround, {angle} view, {pose_definition['description']}"
        elif pose_type in ["nsfw_suggestive", "nsfw_explicit"]:
            prompt = self._build_nsfw_prompt(pose_definition, preserve_clothing)
        else:
            prompt = f"character pose, {pose_definition['description']}"

        # Add quality tags
        prompt += ", masterpiece, best quality, highly detailed, sharp focus"

        workflow = {
            "1": {  # Load checkpoint
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "realisticVision-v51.safetensors"  # Or specialized model for NSFW
                }
            },
            "2": {  # Character reference image
                "class_type": "LoadImage",
                "inputs": {
                    "image": character_image_path
                }
            },
            "3": {  # IPAdapter for face consistency
                "class_type": "IPAdapterApplyFaceID",
                "inputs": {
                    "model": ["1", 0],
                    "faceid_image": ["2", 0],
                    "weight": 1.0 if preserve_clothing else 0.8,
                    "weight_faceidv2": 1.0
                }
            },
            "4": {  # Text prompt
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["1", 1],
                    "text": prompt
                }
            },
            "5": {  # Negative prompt
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["1", 1],
                    "text": "bad anatomy, bad hands, missing fingers, extra digits, fewer digits, cropped, worst quality, low quality"
                }
            },
            "6": {  # KSampler
                "class_type": "KSampler",
                "inputs": {
                    "model": ["3", 0],
                    "positive": ["4", 0],
                    "negative": ["5", 0],
                    "seed": self._get_random_seed(),
                    "steps": settings["steps"],
                    "cfg": settings["cfg"],
                    "sampler_name": "euler_ancestral",
                    "scheduler": "normal",
                    "denoise": settings["denoise"],
                    "latent_image": ["7", 0]
                }
            },
            "7": {  # Empty latent
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": 768,
                    "height": 1024,
                    "batch_size": 1
                }
            },
            "8": {  # VAE Decode
                "class_type": "VAEDecode",
                "inputs": {
                    "vae": ["1", 2],
                    "samples": ["6", 0]
                }
            },
            "9": {  # Save Image
                "class_type": "SaveImage",
                "inputs": {
                    "images": ["8", 0],
                    "filename_prefix": f"pose_{pose_type}"
                }
            }
        }

        # Add ControlNet for OpenPose if available
        if self._has_openpose_reference(pose_definition):
            workflow["10"] = {
                "class_type": "ControlNetLoader",
                "inputs": {
                    "control_net_name": "control_v11p_sd15_openpose.pth"
                }
            }
            # Additional ControlNet nodes would be added here

        return workflow

    def _build_nsfw_prompt(self, pose_definition: Dict, preserve_clothing: bool) -> str:
        """
        Build NSFW-appropriate prompt with safety considerations.
        """
        base_prompt = pose_definition["description"]

        if not preserve_clothing:
            # Add artistic/tasteful modifiers for nude content
            base_prompt += ", artistic photography, professional lighting, tasteful composition"
        else:
            # Suggestive but clothed
            base_prompt += ", suggestive pose, alluring, fashion photography"

        return base_prompt

    async def _wait_for_result(self, client: httpx.AsyncClient, prompt_id: str, session_id: str, timeout: int = 120) -> str:
        """
        Wait for ComfyUI to complete generation and return output path.
        Simplified version - production should use websocket monitoring.
        """
        for _ in range(timeout // 5):
            await asyncio.sleep(5)

            try:
                response = await client.get(f"{self.comfyui_url}/history/{prompt_id}")
                if response.status_code == 200:
                    history = response.json()
                    if prompt_id in history:
                        outputs = history[prompt_id].get("outputs", {})
                        for node_outputs in outputs.values():
                            if "images" in node_outputs:
                                return node_outputs["images"][0]["filename"]
            except Exception as e:
                logger.error(f"Error checking result: {e}")

        return None

    def _has_openpose_reference(self, pose_definition: Dict) -> bool:
        """Check if we have an OpenPose reference for this pose"""
        # This would check if pre-generated OpenPose skeleton exists
        # For now, return False to use text-only generation
        return False

    def _get_random_seed(self) -> int:
        """Generate random seed for variety"""
        import random
        return random.randint(0, 2**32 - 1)

    def _save_pose_sheet(self, pose_sheet: Dict):
        """Save pose sheet metadata to tracking file"""
        output_dir = Path("/opt/tower-anime-production/pose_sheets")
        output_dir.mkdir(exist_ok=True, parents=True)

        filename = f"pose_sheet_{pose_sheet['character_id']}_{pose_sheet['session_id']}.json"
        with open(output_dir / filename, 'w') as f:
            json.dump(pose_sheet, f, indent=2)

        logger.info(f"Saved pose sheet: {filename}")

    async def batch_animate_poses(
        self,
        pose_sheet_id: str,
        svd_parameters: Dict,
        animation_api_url: str = "http://127.0.0.1:8331"
    ) -> List[Dict]:
        """
        Animate all poses in a pose sheet using SVD.

        Args:
            pose_sheet_id: ID of the pose sheet to animate
            svd_parameters: SVD animation parameters
            animation_api_url: URL of the animation API

        Returns:
            List of animation results
        """
        # Load pose sheet
        pose_sheet = self._load_pose_sheet(pose_sheet_id)

        animations = []
        async with httpx.AsyncClient(timeout=60.0) as client:
            for pose in pose_sheet["poses"]:
                logger.info(f"Animating pose: {pose['pose_ref']}")

                # Submit to SVD animation endpoint
                response = await client.post(
                    f"{animation_api_url}/api/character-studio/pose/animate-svd",
                    json={
                        "image_path": pose["output_path"],
                        **svd_parameters
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    animations.append({
                        "pose": pose["pose_ref"],
                        "animation_id": result["animation_id"],
                        "status": "submitted"
                    })
                    logger.info(f"  ✓ Submitted animation: {result['animation_id']}")
                else:
                    logger.error(f"  ❌ Failed to animate pose")

                # Rate limiting
                await asyncio.sleep(10)

        return animations

    def _load_pose_sheet(self, pose_sheet_id: str) -> Dict:
        """Load pose sheet metadata from file"""
        pose_sheets_dir = Path("/opt/tower-anime-production/pose_sheets")
        for file in pose_sheets_dir.glob("*.json"):
            with open(file, 'r') as f:
                data = json.load(f)
                if data.get("session_id") == pose_sheet_id:
                    return data
        raise ValueError(f"Pose sheet not found: {pose_sheet_id}")


# Global instance
pose_generator = PoseGenerator()