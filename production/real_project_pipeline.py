#!/usr/bin/env python3
"""
REAL Project Pipeline - Uses anime_production database and actual LoRAs
Connects Tokyo Debt Desire and Cyberpunk Goblin Slayer properly
"""

import os
import json
import time
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import aiohttp
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RealProjectPipeline:
    """Uses ACTUAL anime_production database and trained LoRAs"""

    def __init__(self):
        self.comfyui_url = "http://192.168.50.135:8188"

        # CORRECT DATABASE - anime_production, not tower_consolidated!
        self.db_config = {
            'host': 'localhost',
            'database': 'anime_production',
            'user': 'patrick',
            'password': 'RP78eIrW7cI2jYvL5akt1yurE'
        }

        self.output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
        self.input_dir = Path("/mnt/1TB-storage/ComfyUI/input")

    def get_db_connection(self):
        """Connect to anime_production database"""
        return psycopg2.connect(**self.db_config, cursor_factory=RealDictCursor)

    async def get_character_with_lora(self, character_name: str) -> Optional[Dict[str, Any]]:
        """Get character data INCLUDING their trained LoRA path"""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT c.*, p.name as project_name
            FROM characters c
            JOIN projects p ON c.project_id = p.id
            WHERE c.name = %s
        """, (character_name,))

        character = cursor.fetchone()
        conn.close()

        if character:
            return dict(character)
        return None

    async def generate_character_with_proper_lora(
        self,
        character_name: str,
        scene_description: str = ""
    ) -> Optional[str]:
        """Generate character using their ACTUAL trained LoRA"""

        logger.info(f"🎯 Generating {character_name} with PROPER LoRA")

        # Get character from anime_production DB
        character = await self.get_character_with_lora(character_name)

        if not character:
            logger.error(f"❌ Character {character_name} not found in anime_production DB")
            return None

        logger.info(f"✅ Found {character_name} from project: {character['project_name']}")
        logger.info(f"   LoRA: {character.get('lora_path', 'No LoRA')}")
        logger.info(f"   Trigger: {character.get('lora_trigger', 'No trigger')}")

        # Determine checkpoint based on project
        if "Goblin Slayer" in character['project_name']:
            checkpoint = "counterfeit_v3.safetensors"  # Cyberpunk anime style
        else:  # Tokyo Debt Desire
            checkpoint = "AOM3A1B.safetensors"  # Standard anime style

        # Build prompt with character trigger word if available
        trigger = character.get('lora_trigger', '')
        description = character.get('description', '')

        prompt = f"{trigger} {description} {scene_description}".strip()

        timestamp = int(time.time())
        sanitized_name = character_name.replace(' ', '_')

        workflow = self._create_character_workflow(
            checkpoint=checkpoint,
            lora_path=character.get('lora_path'),
            prompt=prompt,
            seed=timestamp,
            filename_prefix=f"real_{sanitized_name}_{timestamp}"
        )

        # Submit workflow
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.comfyui_url}/prompt",
                json={"prompt": workflow}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    prompt_id = result.get("prompt_id")

                    if prompt_id:
                        # Wait for completion
                        image_path = await self._wait_for_image(
                            f"real_{sanitized_name}_{timestamp}",
                            timeout=180
                        )

                        if image_path:
                            logger.info(f"✅ Generated {character_name}: {image_path}")
                            return image_path
                        else:
                            logger.error(f"❌ Timeout waiting for {character_name}")
                else:
                    error = await response.text()
                    logger.error(f"❌ ComfyUI error: {error}")

        return None

    def _create_character_workflow(
        self,
        checkpoint: str,
        lora_path: Optional[str],
        prompt: str,
        seed: int,
        filename_prefix: str
    ) -> Dict[str, Any]:
        """Create workflow using actual LoRA if available"""

        workflow = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": checkpoint}
            }
        }

        # Add LoRA if character has one
        if lora_path:
            workflow["2"] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": lora_path,
                    "strength_model": 0.8,
                    "strength_clip": 0.8,
                    "model": ["1", 0],
                    "clip": ["1", 1]
                }
            }
            model_connection = ["2", 0]
            clip_connection = ["2", 1]
        else:
            model_connection = ["1", 0]
            clip_connection = ["1", 1]

        # Add rest of workflow
        workflow.update({
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": clip_connection
                }
            },
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": "low quality, blurry, distorted",
                    "clip": clip_connection
                }
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": 768, "height": 768, "batch_size": 1}
            },
            "6": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": 25,
                    "cfg": 7.5,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "denoise": 1.0,
                    "model": model_connection,
                    "positive": ["3", 0],
                    "negative": ["4", 0],
                    "latent_image": ["5", 0]
                }
            },
            "7": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["6", 0],
                    "vae": ["1", 2]
                }
            },
            "8": {
                "class_type": "SaveImage",
                "inputs": {
                    "images": ["7", 0],
                    "filename_prefix": filename_prefix
                }
            }
        })

        return workflow

    async def _wait_for_image(self, prefix: str, timeout: int = 180) -> Optional[str]:
        """Wait for image generation"""
        pattern = f"{prefix}_*.png"
        start_time = time.time()

        while time.time() - start_time < timeout:
            files = list(self.output_dir.glob(pattern))
            if files:
                return str(files[0])
            await asyncio.sleep(5)

        return None

    async def generate_cyberpunk_goblin_slayer_episode(self):
        """Generate episode with Cyberpunk Goblin Slayer characters"""

        logger.info("🎮 CYBERPUNK GOBLIN SLAYER EPISODE")
        logger.info("="*50)

        characters = ["Kai Nakamura", "Ryuu", "Hiroshi"]
        results = []

        for char_name in characters:
            logger.info(f"\n🎯 Generating {char_name}")
            image = await self.generate_character_with_proper_lora(
                char_name,
                "in neon-lit underground goblin hunting scene, cyberpunk setting"
            )

            if image:
                results.append({"character": char_name, "image": image})

                # Generate video with LTX 2B
                video = await self.generate_ltx_video_from_image(
                    image,
                    f"{char_name} hunting cyber goblins in underground Tokyo"
                )

                if video:
                    results[-1]["video"] = video
                    logger.info(f"✅ Video generated: {video}")

        return results

    async def generate_tokyo_debt_desire_episode(self):
        """Generate episode with Tokyo Debt Desire characters"""

        logger.info("💴 TOKYO DEBT DESIRE EPISODE")
        logger.info("="*50)

        # Check who has LoRAs
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.name, c.lora_path
            FROM characters c
            JOIN projects p ON c.project_id = p.id
            WHERE p.name = 'Tokyo Debt Desire'
        """)
        characters = cursor.fetchall()
        conn.close()

        results = []

        for char in characters:
            char_name = char['name']
            logger.info(f"\n🎯 Generating {char_name}")

            # For Mei, use her specific LoRA
            if "Mei" in char_name:
                # Update DB to point to actual LoRA file
                conn = self.get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE characters
                    SET lora_path = 'mei_working_v1.safetensors',
                        lora_trigger = 'mei'
                    WHERE name = %s
                """, (char_name,))
                conn.commit()
                conn.close()

            image = await self.generate_character_with_proper_lora(
                char_name,
                "in Tokyo street dealing with debt collection, dramatic lighting"
            )

            if image:
                results.append({"character": char_name, "image": image})

        return results

    async def generate_ltx_video_from_image(
        self,
        image_path: str,
        scene_description: str
    ) -> Optional[str]:
        """Generate LTX 2B video from character image"""

        # Copy to input directory
        import shutil
        image_name = Path(image_path).name
        input_path = self.input_dir / image_name
        shutil.copy2(image_path, input_path)

        timestamp = int(time.time())

        workflow = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "ltx-2/ltxv-2b-0.9.8-distilled.safetensors"}
            },
            "2": {
                "class_type": "CLIPLoader",
                "inputs": {
                    "clip_name": "t5xxl_fp16.safetensors",
                    "type": "ltxv"
                }
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": scene_description,
                    "clip": ["2", 0]
                }
            },
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": "low quality, static",
                    "clip": ["2", 0]
                }
            },
            "5": {
                "class_type": "LoadImage",
                "inputs": {"image": image_name}
            },
            "6": {
                "class_type": "EmptyLTXVLatentVideo",
                "inputs": {
                    "width": 768,
                    "height": 512,
                    "length": 121,
                    "batch_size": 1
                }
            },
            "7": {
                "class_type": "LTXVImgToVideo",
                "inputs": {
                    "positive": ["3", 0],
                    "negative": ["4", 0],
                    "vae": ["1", 2],
                    "image": ["5", 0],
                    "width": 768,
                    "height": 512,
                    "length": 121,
                    "batch_size": 1,
                    "strength": 0.8
                }
            },
            "8": {
                "class_type": "LTXVConditioning",
                "inputs": {
                    "positive": ["7", 0],
                    "negative": ["7", 1],
                    "frame_rate": 24
                }
            },
            "9": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": timestamp,
                    "steps": 20,
                    "cfg": 3,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "positive": ["8", 0],
                    "negative": ["8", 1],
                    "latent_image": ["6", 0],
                    "model": ["1", 0],
                    "denoise": 0.8
                }
            },
            "10": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["9", 0], "vae": ["1", 2]}
            },
            "11": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": ["10", 0],
                    "frame_rate": 24,
                    "loop_count": 0,
                    "filename_prefix": f"real_video_{timestamp}",
                    "format": "video/h264-mp4",
                    "pingpong": False,
                    "save_output": True
                }
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.comfyui_url}/prompt",
                json={"prompt": workflow}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    prompt_id = result.get("prompt_id")

                    if prompt_id:
                        # Wait for video
                        video_path = await self._wait_for_video(f"real_video_{timestamp}")
                        return video_path

        return None

    async def _wait_for_video(self, prefix: str, timeout: int = 300) -> Optional[str]:
        """Wait for video generation"""
        pattern = f"{prefix}_*.mp4"
        start_time = time.time()

        while time.time() - start_time < timeout:
            files = list(self.output_dir.glob(pattern))
            if files:
                return str(files[0])
            await asyncio.sleep(10)

        return None

async def main():
    """Test REAL project pipeline"""
    pipeline = RealProjectPipeline()

    # Test Cyberpunk Goblin Slayer (has trained LoRAs)
    print("\n" + "="*60)
    print("TESTING CYBERPUNK GOBLIN SLAYER CHARACTERS")
    print("="*60)

    # Just test one character quickly
    kai = await pipeline.generate_character_with_proper_lora(
        "Kai Nakamura",
        "hunting cyber goblins in neon underground"
    )

    if kai:
        print(f"✅ SUCCESS: Kai Nakamura generated with proper LoRA")
        print(f"   Image: {kai}")
    else:
        print("❌ Failed to generate Kai Nakamura")

    # Test Tokyo Debt Desire
    print("\n" + "="*60)
    print("TESTING TOKYO DEBT DESIRE CHARACTERS")
    print("="*60)

    # Update Mei's LoRA path first
    conn = pipeline.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE characters
        SET lora_path = 'mei_working_v1.safetensors',
            lora_trigger = 'mei'
        WHERE name = 'Mei Kobayashi'
    """)
    conn.commit()
    conn.close()

    mei = await pipeline.generate_character_with_proper_lora(
        "Mei Kobayashi",
        "in Tokyo dealing with debt collection"
    )

    if mei:
        print(f"✅ SUCCESS: Mei Kobayashi generated with proper LoRA")
        print(f"   Image: {mei}")
    else:
        print("❌ Failed to generate Mei Kobayashi")

if __name__ == "__main__":
    asyncio.run(main())