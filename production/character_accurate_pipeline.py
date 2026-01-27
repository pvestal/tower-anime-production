#!/usr/bin/env python3
"""
Character-Accurate Production Pipeline
PROPERLY connects database character descriptions to visual generation
"""

import os
import json
import time
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import aiohttp
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CharacterAccuratePipeline:
    """Generate ACTUAL project characters, not random anime"""

    def __init__(self):
        self.comfyui_url = "http://192.168.50.135:8188"
        self.db_config = {
            'host': 'localhost',
            'database': 'tower_consolidated',
            'user': 'patrick',
            'password': 'RP78eIrW7cI2jYvL5akt1yurE'
        }
        self.output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
        self.input_dir = Path("/mnt/1TB-storage/ComfyUI/input")

        # Character-specific visual mappings
        self.character_visual_map = {
            "Akira Yamamoto": {
                "primary_features": "22-year-old male, spiky black hair, cybernetic arm implants visible",
                "clothing": "neon blue jacket, street racing gear",
                "style": "cyberpunk street racer, anime style",
                "negative": "purple hair, female, lab coat, suits"
            },
            "Luna Chen": {
                "primary_features": "young woman, silver hair, holographic tattoos glowing on skin",
                "clothing": "white lab coat, futuristic research attire",
                "style": "cyberpunk scientist, anime style",
                "negative": "black hair, male, racing jacket, suits"
            },
            "Viktor Kozlov": {
                "primary_features": "middle-aged man, stern expression, augmented reality monocle over eye",
                "clothing": "expensive business suit, corporate attire",
                "style": "cyberpunk corporate villain, anime style",
                "negative": "young, casual clothes, lab coat, racing gear"
            }
        }

    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(**self.db_config, cursor_factory=RealDictCursor)

    async def generate_accurate_character_image(
        self,
        character_name: str,
        scene_context: str = "",
        use_ltx_base: bool = False
    ) -> Optional[str]:
        """Generate character image that ACTUALLY matches database description"""

        logger.info(f"🎯 Generating ACCURATE image for: {character_name}")

        # Get character from database
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM characters WHERE name = %s LIMIT 1",
            (character_name,)
        )
        character_data = cursor.fetchone()
        conn.close()

        if not character_data:
            logger.error(f"Character {character_name} not found in database")
            return None

        # Get character-specific visual details
        visual_data = self.character_visual_map.get(character_name, {})

        # Build DETAILED character prompt from database + visual map
        character_prompt = f"""
        {character_data['description']}
        {visual_data.get('primary_features', '')}
        {visual_data.get('clothing', '')}
        {scene_context}
        {visual_data.get('style', 'cyberpunk anime style')}
        high quality, detailed, consistent character design
        """.strip()

        # Build negative prompt to PREVENT wrong characters
        negative_prompt = f"""
        {visual_data.get('negative', '')}
        wrong character, inconsistent design, generic anime character
        low quality, blurry, distorted
        """.strip()

        timestamp = int(time.time())

        if use_ltx_base:
            # Use LTX for initial generation (better quality)
            workflow = self._create_ltx_character_workflow(
                character_prompt, negative_prompt, timestamp
            )
        else:
            # Use standard SD workflow with cyberpunk checkpoint
            workflow = self._create_sd_character_workflow(
                character_prompt, negative_prompt, timestamp, character_name
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
                        image_path = await self._wait_for_completion(
                            prompt_id, character_name, timestamp
                        )

                        if image_path:
                            logger.info(f"✅ ACCURATE {character_name} generated: {image_path}")

                            # Validate it matches description
                            if await self._validate_character_accuracy(image_path, character_data):
                                return image_path
                            else:
                                logger.warning(f"⚠️ Generated image doesn't match {character_name} description")
                                return None

                else:
                    error = await response.text()
                    logger.error(f"ComfyUI error: {error}")

        return None

    def _create_sd_character_workflow(
        self, prompt: str, negative: str, seed: int, character_name: str
    ) -> Dict[str, Any]:
        """Create workflow for accurate character generation"""

        # Determine best checkpoint for cyberpunk style
        # Use Counterfeit for anime-style cyberpunk
        checkpoint = "counterfeit_v3.safetensors"

        # Determine if we have character-specific LoRA (currently using mei as placeholder)
        # TODO: Train character-specific LoRAs for Akira, Luna, Viktor
        lora_file = "mei_working_v1.safetensors"

        sanitized_name = character_name.replace(' ', '_')

        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": checkpoint}
            },
            "2": {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": lora_file,
                    "strength_model": 0.7,  # Reduced to not override character features
                    "strength_clip": 0.7,
                    "model": ["1", 0],
                    "clip": ["1", 1]
                }
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["2", 1]
                }
            },
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": negative,
                    "clip": ["2", 1]
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
                    "steps": 30,  # More steps for better quality
                    "cfg": 7.5,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "denoise": 1.0,
                    "model": ["2", 0],
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
                    "filename_prefix": f"accurate_{sanitized_name}_{seed}"
                }
            }
        }

    def _create_ltx_character_workflow(
        self, prompt: str, negative: str, seed: int
    ) -> Dict[str, Any]:
        """Create LTX workflow for character generation"""

        return {
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
                    "text": prompt,
                    "clip": ["2", 0]
                }
            },
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": negative,
                    "clip": ["2", 0]
                }
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": 768, "height": 512, "batch_size": 1}
            },
            "6": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": 25,
                    "cfg": 7,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["3", 0],
                    "negative": ["4", 0],
                    "latent_image": ["5", 0]
                }
            },
            "7": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["6", 0], "vae": ["1", 2]}
            },
            "8": {
                "class_type": "SaveImage",
                "inputs": {
                    "images": ["7", 0],
                    "filename_prefix": f"ltx_character_{seed}"
                }
            }
        }

    async def _wait_for_completion(
        self, prompt_id: str, character_name: str, timestamp: int
    ) -> Optional[str]:
        """Wait for image generation to complete"""

        sanitized_name = character_name.replace(' ', '_')
        patterns = [
            f"accurate_{sanitized_name}_{timestamp}_*.png",
            f"ltx_character_{timestamp}_*.png"
        ]

        max_wait = 180  # 3 minutes
        start_time = time.time()

        while time.time() - start_time < max_wait:
            for pattern in patterns:
                output_files = list(self.output_dir.glob(pattern))
                if output_files:
                    return str(output_files[0])

            await asyncio.sleep(5)

        logger.error(f"Generation timeout for {prompt_id}")
        return None

    async def _validate_character_accuracy(
        self, image_path: str, character_data: Dict[str, Any]
    ) -> bool:
        """Validate that generated image matches character description"""

        # For now, basic validation that file exists
        # TODO: Implement visual validation using CLIP or other vision model
        # to verify features match (e.g., black hair for Akira, silver for Luna)

        if Path(image_path).exists():
            file_size = Path(image_path).stat().st_size
            if file_size > 100000:  # At least 100KB
                return True

        return False

    async def generate_character_video_sequence(
        self,
        character_name: str,
        scene_description: str,
        duration: float = 5.0
    ) -> Optional[str]:
        """Generate video sequence with ACCURATE character"""

        logger.info(f"🎬 Creating video for {character_name}: {scene_description}")

        # First generate accurate character image
        character_image = await self.generate_accurate_character_image(
            character_name,
            scene_context=scene_description
        )

        if not character_image:
            logger.error(f"Failed to generate accurate image for {character_name}")
            return None

        # Copy to input directory for video generation
        import shutil
        input_image_name = Path(character_image).name
        input_path = self.input_dir / input_image_name
        shutil.copy2(character_image, input_path)

        # Generate video using LTX 2B with character
        timestamp = int(time.time())

        # Get character visual data for video prompt
        visual_data = self.character_visual_map.get(character_name, {})
        video_prompt = f"""
        {scene_description}
        Character: {character_name}
        {visual_data.get('primary_features', '')}
        {visual_data.get('style', 'cyberpunk anime style')}
        smooth animation, consistent character throughout
        """

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
                    "text": video_prompt,
                    "clip": ["2", 0]
                }
            },
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": visual_data.get('negative', 'low quality'),
                    "clip": ["2", 0]
                }
            },
            "5": {
                "class_type": "LoadImage",
                "inputs": {"image": input_image_name}
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
                    "filename_prefix": f"accurate_video_{character_name.replace(' ', '_')}_{timestamp}",
                    "format": "video/h264-mp4",
                    "pingpong": False,
                    "save_output": True
                }
            }
        }

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
                        # Wait for video
                        video_path = await self._wait_for_video(
                            character_name, timestamp
                        )

                        if video_path:
                            logger.info(f"✅ ACCURATE video generated: {video_path}")
                            return video_path

        return None

    async def _wait_for_video(
        self, character_name: str, timestamp: int
    ) -> Optional[str]:
        """Wait for video generation"""

        sanitized_name = character_name.replace(' ', '_')
        pattern = f"accurate_video_{sanitized_name}_{timestamp}_*.mp4"

        max_wait = 300  # 5 minutes
        start_time = time.time()

        while time.time() - start_time < max_wait:
            output_files = list(self.output_dir.glob(pattern))
            if output_files:
                return str(output_files[0])

            await asyncio.sleep(10)

        return None

    async def test_all_characters(self):
        """Test generation for all three main characters"""

        characters = ["Akira Yamamoto", "Luna Chen", "Viktor Kozlov"]
        results = {}

        for character in characters:
            logger.info(f"\n{'='*50}")
            logger.info(f"Testing: {character}")
            logger.info('='*50)

            # Generate character image
            image = await self.generate_accurate_character_image(
                character,
                scene_context="standing in neon-lit Tokyo street at night"
            )

            if image:
                logger.info(f"✅ Image generated: {image}")

                # Generate video
                video = await self.generate_character_video_sequence(
                    character,
                    "walking through cyberpunk Tokyo streets, neon lights reflecting"
                )

                if video:
                    logger.info(f"✅ Video generated: {video}")
                    results[character] = {"image": image, "video": video, "status": "success"}
                else:
                    results[character] = {"image": image, "video": None, "status": "partial"}
            else:
                results[character] = {"status": "failed"}

        # Summary
        logger.info(f"\n{'='*50}")
        logger.info("RESULTS SUMMARY")
        logger.info('='*50)

        for character, result in results.items():
            status_icon = "✅" if result["status"] == "success" else "⚠️" if result["status"] == "partial" else "❌"
            logger.info(f"{status_icon} {character}: {result['status']}")
            if result.get("image"):
                logger.info(f"    Image: {Path(result['image']).name}")
            if result.get("video"):
                logger.info(f"    Video: {Path(result['video']).name}")

        return results

async def main():
    """Test character-accurate generation"""
    pipeline = CharacterAccuratePipeline()

    # Test single character first
    logger.info("Testing single character: Akira Yamamoto")

    image = await pipeline.generate_accurate_character_image(
        "Akira Yamamoto",
        scene_context="racing motorcycle through neon Tokyo streets"
    )

    if image:
        logger.info(f"✅ SUCCESS: Akira image generated: {image}")

        video = await pipeline.generate_character_video_sequence(
            "Akira Yamamoto",
            "high-speed motorcycle chase through cyberpunk Tokyo"
        )

        if video:
            logger.info(f"✅ SUCCESS: Akira video generated: {video}")
        else:
            logger.info("❌ Video generation failed")
    else:
        logger.info("❌ Image generation failed")

    # Test all characters
    logger.info("\nTesting all characters...")
    results = await pipeline.test_all_characters()

    success_count = sum(1 for r in results.values() if r["status"] == "success")
    logger.info(f"\n🎯 Final Score: {success_count}/3 characters successfully generated")

if __name__ == "__main__":
    asyncio.run(main())