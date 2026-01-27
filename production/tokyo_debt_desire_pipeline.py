#!/usr/bin/env python3
"""
Tokyo Debt Desire Complete Pipeline
Connects all models, LoRAs, and content settings for the project
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

class TokyoDebtDesirePipeline:
    """Complete pipeline for Tokyo Debt Desire with all content types"""

    def __init__(self):
        self.comfyui_url = "http://192.168.50.135:8188"
        self.db_config = {
            'host': 'localhost',
            'database': 'anime_production',
            'user': 'patrick',
            'password': 'RP78eIrW7cI2jYvL5akt1yurE'
        }
        self.output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
        self.input_dir = Path("/mnt/1TB-storage/ComfyUI/input")

        # Available checkpoints for different content types
        self.checkpoints = {
            'sfw': 'AOM3A1B.safetensors',  # Safe for work anime
            'realistic': 'chilloutmix_NiPrunedFp32Fix.safetensors',  # Realistic style
            'nsfw_anime': 'Counterfeit-V2.5.safetensors',  # Less restricted anime
            'nsfw_realistic': 'realisticVision_v51.safetensors'  # Photorealistic
        }

        # Mei-specific LoRAs
        self.mei_loras = {
            'base': 'mei_working_v1.safetensors',
            'body': 'mei_body.safetensors',
            'face': 'mei_face.safetensors',
            'real': 'mei_real_v3.safetensors'
        }

    def get_db_connection(self):
        return psycopg2.connect(**self.db_config, cursor_factory=RealDictCursor)

    async def generate_tokyo_debt_character(
        self,
        character_name: str,
        scene: str,
        content_rating: str = "sfw",
        style: str = "anime"
    ) -> Optional[str]:
        """Generate Tokyo Debt Desire character with appropriate content settings"""

        logger.info(f"🎌 Generating {character_name} for Tokyo Debt Desire")
        logger.info(f"   Content rating: {content_rating}")
        logger.info(f"   Style: {style}")
        logger.info(f"   Scene: {scene}")

        # Get character from database
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.*, p.name as project_name
            FROM characters c
            JOIN projects p ON c.project_id = p.id
            WHERE c.name = %s AND p.name = 'Tokyo Debt Desire'
        """, (character_name,))
        character = cursor.fetchone()
        conn.close()

        if not character:
            logger.error(f"Character {character_name} not found in Tokyo Debt Desire")
            return None

        # Determine checkpoint based on content and style
        if content_rating == "nsfw":
            checkpoint = self.checkpoints['nsfw_realistic'] if style == "realistic" else self.checkpoints['nsfw_anime']
        else:
            checkpoint = self.checkpoints['realistic'] if style == "realistic" else self.checkpoints['sfw']

        # Determine LoRA for Mei
        lora_file = None
        if "Mei" in character_name or "mei" in character_name.lower():
            if content_rating == "nsfw" and style == "realistic":
                lora_file = self.mei_loras['real']
            elif content_rating == "nsfw":
                lora_file = self.mei_loras['body']
            else:
                lora_file = self.mei_loras['base']

        # Build prompt
        base_description = character.get('description', '')
        trigger = character.get('lora_trigger', '')

        # Add content-specific modifiers
        if content_rating == "nsfw":
            prompt = f"{trigger} {base_description}, {scene}, detailed, high quality"
            negative = "censored, cropped, low quality, blurry"
        else:
            prompt = f"{trigger} {base_description}, {scene}, masterpiece, best quality"
            negative = "nsfw, nude, explicit, low quality, blurry"

        timestamp = int(time.time())
        sanitized_name = character_name.replace(' ', '_')
        filename = f"tdd_{sanitized_name}_{content_rating}_{timestamp}"

        workflow = self._create_workflow(
            checkpoint=checkpoint,
            lora_file=lora_file,
            prompt=prompt,
            negative=negative,
            seed=timestamp,
            filename=filename
        )

        # Submit to ComfyUI
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.comfyui_url}/prompt",
                json={"prompt": workflow}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    prompt_id = result.get("prompt_id")

                    if prompt_id:
                        image_path = await self._wait_for_image(filename)
                        if image_path:
                            logger.info(f"✅ Generated: {image_path}")

                            # Update database with generation
                            await self._log_generation(character_name, image_path, content_rating)

                            return image_path

        return None

    def _create_workflow(
        self,
        checkpoint: str,
        lora_file: Optional[str],
        prompt: str,
        negative: str,
        seed: int,
        filename: str
    ) -> Dict[str, Any]:
        """Create ComfyUI workflow"""

        workflow = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": checkpoint}
            }
        }

        # Add LoRA if specified
        if lora_file:
            workflow["2"] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": lora_file,
                    "strength_model": 0.85,
                    "strength_clip": 0.85,
                    "model": ["1", 0],
                    "clip": ["1", 1]
                }
            }
            model_connection = ["2", 0]
            clip_connection = ["2", 1]
        else:
            model_connection = ["1", 0]
            clip_connection = ["1", 1]

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
                    "text": negative,
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
                    "steps": 30,
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
                    "filename_prefix": filename
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

    async def _log_generation(self, character: str, file_path: str, rating: str):
        """Log generation to database"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO generated_assets (file_path, file_type, metadata)
            VALUES (%s, %s, %s)
        """, (
            file_path,
            'image',
            json.dumps({
                'character': character,
                'project': 'Tokyo Debt Desire',
                'content_rating': rating,
                'timestamp': time.time()
            })
        ))
        conn.commit()
        conn.close()

    async def test_all_content_types(self):
        """Test generation with different content ratings"""

        test_cases = [
            ("Mei Kobayashi", "at work in office", "sfw", "anime"),
            ("Mei Kobayashi", "casual at home", "sfw", "realistic"),
            ("Rina Suzuki", "dealing with debt collector", "sfw", "anime"),
            # Can add nsfw test cases if needed
        ]

        results = []

        for character, scene, rating, style in test_cases:
            logger.info(f"\n{'='*50}")
            logger.info(f"Testing: {character} - {rating} - {style}")

            image = await self.generate_tokyo_debt_character(
                character, scene, rating, style
            )

            if image:
                results.append({
                    "character": character,
                    "rating": rating,
                    "style": style,
                    "image": image,
                    "status": "success"
                })
            else:
                results.append({
                    "character": character,
                    "rating": rating,
                    "style": style,
                    "status": "failed"
                })

        # Summary
        logger.info(f"\n{'='*50}")
        logger.info("RESULTS SUMMARY")
        logger.info('='*50)

        success_count = sum(1 for r in results if r["status"] == "success")
        logger.info(f"Success rate: {success_count}/{len(results)}")

        for result in results:
            status_icon = "✅" if result["status"] == "success" else "❌"
            logger.info(f"{status_icon} {result['character']} ({result['rating']}/{result['style']}): {result['status']}")

        return results

async def main():
    """Test Tokyo Debt Desire pipeline"""
    pipeline = TokyoDebtDesirePipeline()

    # Quick test with Mei
    logger.info("Testing Tokyo Debt Desire Pipeline")
    logger.info("="*60)

    # Test SFW generation
    mei_sfw = await pipeline.generate_tokyo_debt_character(
        "Mei Kobayashi",
        "working at desk in office",
        content_rating="sfw",
        style="anime"
    )

    if mei_sfw:
        logger.info(f"✅ SUCCESS: Mei SFW generated")
    else:
        logger.info("❌ Failed to generate Mei SFW")

    # Test realistic style
    mei_realistic = await pipeline.generate_tokyo_debt_character(
        "Mei Kobayashi",
        "casual outfit at home",
        content_rating="sfw",
        style="realistic"
    )

    if mei_realistic:
        logger.info(f"✅ SUCCESS: Mei realistic generated")
    else:
        logger.info("❌ Failed to generate Mei realistic")

if __name__ == "__main__":
    asyncio.run(main())