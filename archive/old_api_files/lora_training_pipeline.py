#!/usr/bin/env python3
"""
Tower LoRA Training Pipeline
Automated LoRA training system for anime characters using ComfyUI
"""

import asyncio
import aiohttp
import json
import os
import time
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
import shutil
from PIL import Image
import requests
import uuid
from dataclasses import dataclass

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TrainingConfig:
    """Configuration for LoRA training parameters"""
    resolution: int = 512
    batch_size: int = 1
    steps: int = 1000
    learning_rate: float = 0.0001
    network_dim: int = 128
    network_alpha: int = 64
    train_batch_size: int = 1
    optimizer: str = "AdamW8bit"

class LoRATrainingPipeline:
    """
    Comprehensive LoRA training pipeline for anime characters
    """

    def __init__(self):
        self.comfyui_base_url = "http://localhost:8188"
        self.db_config = {
            'host': 'localhost',
            'database': 'anime_production',
            'user': 'patrick',
            'password': 'RP78eIrW7cI2jYvL5akt1yurE',
            'port': 5432
        }
        self.storage_base = Path("/mnt/1TB-storage/ComfyUI")
        self.models_dir = self.storage_base / "models" / "loras"
        self.training_data_dir = self.storage_base / "training_data"
        self.output_dir = self.storage_base / "output"

        # Ensure directories exist
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.training_data_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Training configuration
        self.config = TrainingConfig()

    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(**self.db_config)

    async def get_characters_needing_training(self) -> List[Dict]:
        """Get list of characters that need LoRA training"""
        conn = self.get_db_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Get characters without completed training jobs
            query = """
                SELECT DISTINCT c.id, c.name, c.description, c.design_prompt
                FROM characters c
                LEFT JOIN character_training_jobs ctj ON c.id = ctj.character_id
                    AND ctj.status = 'completed'
                WHERE ctj.id IS NULL
                AND c.name IS NOT NULL
                ORDER BY c.id
            """

            cursor.execute(query)
            characters = cursor.fetchall()

            logger.info(f"Found {len(characters)} characters needing LoRA training")
            return [dict(char) for char in characters]

        finally:
            conn.close()

    async def generate_training_images(self, character_id: int, character_name: str,
                                     design_prompt: str, count: int = 20) -> List[str]:
        """
        Generate training images for a character using ComfyUI
        """
        logger.info(f"Generating {count} training images for {character_name}")

        # Create character training directory
        char_dir = self.training_data_dir / f"character_{character_id}_{character_name.lower().replace(' ', '_')}"
        char_dir.mkdir(exist_ok=True)

        generated_images = []

        # Training prompts for diverse poses and expressions
        training_prompts = [
            f"{design_prompt}, front view, standing pose, neutral expression",
            f"{design_prompt}, side view, profile shot, slight smile",
            f"{design_prompt}, three-quarter view, confident pose, determined expression",
            f"{design_prompt}, back view, looking over shoulder, mysterious expression",
            f"{design_prompt}, sitting pose, relaxed expression, casual outfit",
            f"{design_prompt}, action pose, dynamic stance, focused expression",
            f"{design_prompt}, portrait shot, close-up face, happy expression",
            f"{design_prompt}, full body, walking pose, cheerful expression",
            f"{design_prompt}, combat stance, serious expression, battle ready",
            f"{design_prompt}, casual pose, arms crossed, confident smile",
            f"{design_prompt}, kneeling pose, thoughtful expression, gentle smile",
            f"{design_prompt}, jumping pose, excited expression, energetic",
            f"{design_prompt}, sitting cross-legged, meditative pose, calm expression",
            f"{design_prompt}, running pose, determined expression, action shot",
            f"{design_prompt}, pointing gesture, surprised expression, anime style",
            f"{design_prompt}, waving pose, friendly expression, welcoming gesture",
            f"{design_prompt}, defensive pose, alert expression, ready stance",
            f"{design_prompt}, victory pose, triumphant expression, celebrating",
            f"{design_prompt}, resting pose, tired expression, catching breath",
            f"{design_prompt}, formal pose, elegant stance, sophisticated expression"
        ]

        for i, prompt in enumerate(training_prompts[:count]):
            try:
                # Generate image using ComfyUI API
                image_path = await self.generate_single_image(prompt, character_name, i)
                if image_path:
                    # Move to training directory
                    dest_path = char_dir / f"{character_name}_{i:03d}.png"
                    shutil.copy2(image_path, dest_path)
                    generated_images.append(str(dest_path))

                    # Create corresponding caption file
                    caption_path = char_dir / f"{character_name}_{i:03d}.txt"
                    with open(caption_path, 'w') as f:
                        f.write(f"{character_name}, {prompt}")

                await asyncio.sleep(2)  # Rate limiting

            except Exception as e:
                logger.error(f"Error generating image {i} for {character_name}: {e}")
                continue

        logger.info(f"Generated {len(generated_images)} images for {character_name}")
        return generated_images

    async def generate_single_image(self, prompt: str, character_name: str, index: int) -> Optional[str]:
        """Generate a single image using ComfyUI API"""

        # Basic ComfyUI workflow for image generation
        workflow = {
            "3": {
                "inputs": {
                    "seed": 42 + index,
                    "steps": 20,
                    "cfg": 8.0,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0]
                },
                "class_type": "KSampler",
                "_meta": {"title": "KSampler"}
            },
            "4": {
                "inputs": {
                    "ckpt_name": "AOM3A1B.safetensors"
                },
                "class_type": "CheckpointLoaderSimple",
                "_meta": {"title": "Load Checkpoint"}
            },
            "5": {
                "inputs": {
                    "width": 512,
                    "height": 512,
                    "batch_size": 1
                },
                "class_type": "EmptyLatentImage",
                "_meta": {"title": "Empty Latent Image"}
            },
            "6": {
                "inputs": {
                    "text": f"{prompt}, anime style, high quality, detailed, masterpiece",
                    "clip": ["4", 1]
                },
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "CLIP Text Encode (Prompt)"}
            },
            "7": {
                "inputs": {
                    "text": "nsfw, nude, naked, low quality, blurry, distorted, deformed",
                    "clip": ["4", 1]
                },
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "CLIP Text Encode (Prompt)"}
            },
            "8": {
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2]
                },
                "class_type": "VAEDecode",
                "_meta": {"title": "VAE Decode"}
            },
            "9": {
                "inputs": {
                    "filename_prefix": f"{character_name}_training",
                    "images": ["8", 0]
                },
                "class_type": "SaveImage",
                "_meta": {"title": "Save Image"}
            }
        }

        try:
            # Queue prompt
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.comfyui_base_url}/prompt",
                    json={"prompt": workflow}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        prompt_id = result["prompt_id"]

                        # Wait for completion and get result
                        image_path = await self.wait_for_completion(session, prompt_id, character_name, index)
                        return image_path
                    else:
                        logger.error(f"Failed to queue prompt: {response.status}")
                        return None

        except Exception as e:
            logger.error(f"Error in generate_single_image: {e}")
            return None

    async def wait_for_completion(self, session: aiohttp.ClientSession, prompt_id: str,
                                character_name: str, index: int) -> Optional[str]:
        """Wait for ComfyUI to complete generation and return image path"""
        max_wait = 120  # 2 minutes timeout
        wait_time = 0

        while wait_time < max_wait:
            try:
                async with session.get(f"{self.comfyui_base_url}/history/{prompt_id}") as response:
                    if response.status == 200:
                        history = await response.json()

                        if prompt_id in history and 'outputs' in history[prompt_id]:
                            outputs = history[prompt_id]['outputs']

                            # Find the SaveImage node output
                            for node_id, output in outputs.items():
                                if 'images' in output:
                                    for image_info in output['images']:
                                        filename = image_info['filename']
                                        subfolder = image_info.get('subfolder', '')

                                        # Construct full path
                                        if subfolder:
                                            image_path = self.output_dir / subfolder / filename
                                        else:
                                            image_path = self.output_dir / filename

                                        if image_path.exists():
                                            return str(image_path)

                await asyncio.sleep(2)
                wait_time += 2

            except Exception as e:
                logger.error(f"Error checking completion status: {e}")
                await asyncio.sleep(2)
                wait_time += 2

        logger.error(f"Timeout waiting for image generation completion")
        return None

    async def start_lora_training(self, character_id: int, character_name: str,
                                training_images: List[str]) -> bool:
        """
        Start LoRA training process using Kohya training scripts
        """
        logger.info(f"Starting LoRA training for {character_name}")

        char_name_clean = character_name.lower().replace(' ', '_')
        training_dir = self.training_data_dir / f"character_{character_id}_{char_name_clean}"

        # Update training job status to 'in_progress'
        await self.update_training_status(character_id, 'in_progress', training_images)

        try:
            # Create training configuration
            config_path = await self.create_training_config(character_id, training_dir, character_name)

            # Start training using Kohya scripts
            training_success = await self.execute_kohya_training(config_path, character_name)

            if training_success:
                # Update status to completed
                model_path = self.models_dir / f"{char_name_clean}_lora_v1.safetensors"
                await self.update_training_status(character_id, 'completed', training_images, str(model_path))
                logger.info(f"LoRA training completed for {character_name}")
                return True
            else:
                await self.update_training_status(character_id, 'failed', training_images)
                logger.error(f"LoRA training failed for {character_name}")
                return False

        except Exception as e:
            logger.error(f"Error in LoRA training for {character_name}: {e}")
            await self.update_training_status(character_id, 'failed', training_images)
            return False

    async def create_training_config(self, character_id: int, training_dir: Path,
                                   character_name: str) -> str:
        """Create Kohya training configuration file"""

        char_name_clean = character_name.lower().replace(' ', '_')
        config = {
            "train_data_dir": str(training_dir),
            "output_dir": str(self.models_dir),
            "output_name": f"{char_name_clean}_lora_v1",
            "max_train_epochs": 10,
            "save_every_n_epochs": 5,
            "train_batch_size": self.config.train_batch_size,
            "learning_rate": self.config.learning_rate,
            "lr_scheduler": "cosine_with_restarts",
            "network_module": "networks.lora",
            "network_dim": self.config.network_dim,
            "network_alpha": self.config.network_alpha,
            "resolution": f"{self.config.resolution},{self.config.resolution}",
            "enable_bucket": True,
            "min_bucket_reso": 320,
            "max_bucket_reso": 1280,
            "bucket_reso_steps": 64,
            "bucket_no_upscale": True,
            "mixed_precision": "fp16",
            "save_precision": "fp16",
            "optimizer_type": self.config.optimizer,
            "xformers": True,
            "clip_skip": 2,
            "prior_loss_weight": 1.0,
            "max_token_length": 225,
            "v_parameterization": False,
            "cache_latents": True,
            "seed": 42
        }

        config_path = training_dir / "training_config.toml"

        # Write TOML config file
        with open(config_path, 'w') as f:
            for key, value in config.items():
                if isinstance(value, str):
                    f.write(f'{key} = "{value}"\n')
                elif isinstance(value, bool):
                    f.write(f'{key} = {str(value).lower()}\n')
                else:
                    f.write(f'{key} = {value}\n')

        return str(config_path)

    async def execute_kohya_training(self, config_path: str, character_name: str) -> bool:
        """Execute Kohya LoRA training"""
        try:
            # Use the Kohya training script from the system
            kohya_script = "/opt/tower-anime-production/training/kohya_real/train_network.py"

            if not os.path.exists(kohya_script):
                logger.error(f"Kohya training script not found at {kohya_script}")
                return False

            # Create training command
            cmd = [
                "python3",
                kohya_script,
                "--config_file", config_path
            ]

            logger.info(f"Starting training with command: {' '.join(cmd)}")

            # Execute training (this is a long-running process)
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/opt/tower-anime-production/training/kohya_real"
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(f"Training completed successfully for {character_name}")
                return True
            else:
                logger.error(f"Training failed for {character_name}: {stderr.decode()}")
                return False

        except Exception as e:
            logger.error(f"Error executing Kohya training: {e}")
            return False

    async def update_training_status(self, character_id: int, status: str,
                                   images: List[str] = None, model_path: str = None):
        """Update training job status in database"""
        conn = self.get_db_connection()
        try:
            cursor = conn.cursor()

            if status == 'in_progress':
                # Create new training job
                query = """
                    INSERT INTO character_training_jobs
                    (character_id, target_asset_type, status, generated_images, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (
                    character_id, 'lora_v1', status, images or [],
                    datetime.now(), datetime.now()
                ))
            else:
                # Update existing training job
                if model_path:
                    query = """
                        UPDATE character_training_jobs
                        SET status = %s, trained_model_path = %s, updated_at = %s
                        WHERE character_id = %s AND target_asset_type = 'lora_v1'
                    """
                    cursor.execute(query, (status, model_path, datetime.now(), character_id))
                else:
                    query = """
                        UPDATE character_training_jobs
                        SET status = %s, updated_at = %s
                        WHERE character_id = %s AND target_asset_type = 'lora_v1'
                    """
                    cursor.execute(query, (status, datetime.now(), character_id))

            conn.commit()
            logger.info(f"Updated training status for character {character_id}: {status}")

        except Exception as e:
            logger.error(f"Error updating training status: {e}")
            conn.rollback()
        finally:
            conn.close()

    async def process_character_queue(self):
        """Process all characters needing LoRA training"""
        characters = await self.get_characters_needing_training()

        logger.info(f"Processing {len(characters)} characters for LoRA training")

        for character in characters:
            character_id = character['id']
            character_name = character['name']
            design_prompt = character['design_prompt'] or character['description'] or f"anime character named {character_name}"

            try:
                logger.info(f"Starting training pipeline for {character_name} (ID: {character_id})")

                # Step 1: Generate training images
                training_images = await self.generate_training_images(
                    character_id, character_name, design_prompt
                )

                if not training_images:
                    logger.error(f"No training images generated for {character_name}")
                    continue

                # Step 2: Start LoRA training
                success = await self.start_lora_training(character_id, character_name, training_images)

                if success:
                    logger.info(f"Successfully completed LoRA training for {character_name}")
                else:
                    logger.error(f"Failed to complete LoRA training for {character_name}")

            except Exception as e:
                logger.error(f"Error processing character {character_name}: {e}")
                continue

        logger.info("Completed processing character training queue")


async def main():
    """Main execution function"""
    pipeline = LoRATrainingPipeline()

    logger.info("Starting Tower LoRA Training Pipeline")
    await pipeline.process_character_queue()
    logger.info("LoRA Training Pipeline completed")


if __name__ == "__main__":
    asyncio.run(main())