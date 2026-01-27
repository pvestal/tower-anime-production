#!/usr/bin/env python3
"""
Anime Production Manager
Orchestrates the entire anime production workflow with LoRAs
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
import psycopg2
from datetime import datetime
import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnimeProductionManager:
    """Manages the complete anime production pipeline"""

    def __init__(self):
        self.comfyui_url = "http://localhost:8188"
        self.db_config = {
            "host": "localhost",
            "database": "anime_production",
            "user": "patrick",
            "password": "RP78eIrW7cI2jYvL5akt1yurE"
        }

        # Production settings
        self.quality_presets = {
            "preview": {
                "width": 512,
                "height": 384,
                "frames": 25,  # 1 second
                "steps": 10,
                "cfg": 3.5
            },
            "standard": {
                "width": 768,
                "height": 512,
                "frames": 49,  # 2 seconds
                "steps": 15,
                "cfg": 4.0
            },
            "high": {
                "width": 1024,
                "height": 768,
                "frames": 121,  # 5 seconds
                "steps": 25,
                "cfg": 4.5
            }
        }

        # LoRA combinations for different scene types
        self.scene_recipes = {
            "action_fight": {
                "base_loras": [],  # No action LoRA yet
                "strengths": [],
                "prompt_template": "{character} engaged in martial arts combat, dynamic movement, action scene"
            },
            "intimate_scene": {
                "base_loras": ["kiss_ltx2_lora.safetensors"],
                "strengths": [0.7],
                "prompt_template": "{character} in intimate moment, romantic scene, kissing"
            },
            "dialogue": {
                "base_loras": [],
                "strengths": [],
                "prompt_template": "{character} talking, facial expression, dialogue scene"
            },
            "transformation": {
                "base_loras": ["DreamLTXV.safetensors"],
                "strengths": [0.8],
                "prompt_template": "{character} transforming, magical effects, glowing aura, dream sequence"
            },
            "nsfw": {
                "base_loras": ["ltx2_nsfwfurry_lora_step_15000.safetensors"],
                "strengths": [0.6],
                "prompt_template": "{character} in adult scene, nsfw content"
            }
        }

    async def generate_character_reference_sheet(self, character_name: str) -> Dict:
        """Generate reference sheet for a character using multiple angles"""

        angles = [
            "front view, facing camera",
            "side profile, looking left",
            "three quarter view",
            "back view",
            "close-up face portrait"
        ]

        results = []

        async with aiohttp.ClientSession() as session:
            for angle in angles:
                workflow = self._create_character_workflow(
                    character_name,
                    f"{character_name}, {angle}, character reference, high detail",
                    quality="standard"
                )

                async with session.post(
                    f"{self.comfyui_url}/prompt",
                    json={"prompt": workflow}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        results.append({
                            "angle": angle,
                            "prompt_id": result["prompt_id"]
                        })

        return {
            "character": character_name,
            "references": results,
            "timestamp": datetime.now().isoformat()
        }

    def _create_character_workflow(self,
                                  character_name: str,
                                  prompt: str,
                                  quality: str = "standard",
                                  additional_loras: List[str] = None) -> Dict:
        """Create workflow for character generation"""

        preset = self.quality_presets[quality]

        workflow = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "ltxv-2b-fp8.safetensors"}
            },
            "2": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": "t5xxl_fp16.safetensors", "type": "ltxv"}
            }
        }

        # Check if we have a character LoRA
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT name, trigger_word FROM lora_models
            WHERE type = 'character' AND name ILIKE %s
        """, (f"%{character_name.replace(' ', '_')}%",))

        character_lora = cursor.fetchone()
        conn.close()

        prev_model = ["1", 0]
        prev_clip = ["2", 0]
        node_counter = 3

        if character_lora:
            workflow[str(node_counter)] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": character_lora[0] + ".safetensors",
                    "strength_model": 1.0,
                    "strength_clip": 1.0,
                    "model": prev_model,
                    "clip": prev_clip
                }
            }
            prev_model = [str(node_counter), 0]
            prev_clip = [str(node_counter), 1]
            node_counter += 1

            # Update prompt with trigger word
            prompt = f"{character_lora[1]}, {prompt}"

        # Add additional LoRAs if specified
        if additional_loras:
            for lora_name, strength in additional_loras:
                workflow[str(node_counter)] = {
                    "class_type": "LoraLoader",
                    "inputs": {
                        "lora_name": lora_name,
                        "strength_model": strength,
                        "strength_clip": strength * 0.8,
                        "model": prev_model,
                        "clip": prev_clip
                    }
                }
                prev_model = [str(node_counter), 0]
                prev_clip = [str(node_counter), 1]
                node_counter += 1

        # Generation nodes
        workflow.update({
            str(node_counter): {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": prompt, "clip": prev_clip}
            },
            str(node_counter + 1): {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "low quality, blurry, distorted", "clip": prev_clip}
            },
            str(node_counter + 2): {
                "class_type": "EmptyLTXVLatentVideo",
                "inputs": {
                    "width": preset["width"],
                    "height": preset["height"],
                    "length": preset["frames"],
                    "batch_size": 1
                }
            },
            str(node_counter + 3): {
                "class_type": "LTXVConditioning",
                "inputs": {
                    "positive": [str(node_counter), 0],
                    "negative": [str(node_counter + 1), 0],
                    "frame_rate": 24
                }
            },
            str(node_counter + 4): {
                "class_type": "KSampler",
                "inputs": {
                    "seed": int(datetime.now().timestamp()),
                    "steps": preset["steps"],
                    "cfg": preset["cfg"],
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "denoise": 1.0,
                    "model": prev_model,
                    "positive": [str(node_counter + 3), 0],
                    "negative": [str(node_counter + 3), 1],
                    "latent_image": [str(node_counter + 2), 0]
                }
            },
            str(node_counter + 5): {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": [str(node_counter + 4), 0],
                    "vae": ["1", 2]
                }
            },
            str(node_counter + 6): {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": [str(node_counter + 5), 0],
                    "frame_rate": 24,
                    "loop_count": 0,
                    "filename_prefix": f"anime_{character_name.replace(' ', '_')}_{int(datetime.now().timestamp())}",
                    "format": "video/h264-mp4",
                    "pingpong": False,
                    "save_output": True
                }
            }
        })

        return workflow

    async def produce_episode_scene(self,
                                   episode_id: int,
                                   scene_number: int,
                                   scene_type: str,
                                   character_names: List[str],
                                   description: str) -> Dict:
        """Produce a single scene for an episode"""

        # Get scene recipe
        recipe = self.scene_recipes.get(scene_type, self.scene_recipes["dialogue"])

        # Build prompt
        characters = " and ".join(character_names)
        prompt = recipe["prompt_template"].format(character=characters)
        prompt = f"{prompt}, {description}"

        # Determine quality based on scene importance
        quality = "standard" if scene_type != "dialogue" else "preview"

        # Add scene-specific LoRAs
        additional_loras = list(zip(recipe["base_loras"], recipe["strengths"]))

        # Create workflow
        workflow = self._create_character_workflow(
            character_names[0] if character_names else "character",
            prompt,
            quality=quality,
            additional_loras=additional_loras if additional_loras else None
        )

        # Submit generation
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.comfyui_url}/prompt",
                json={"prompt": workflow}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    prompt_id = result["prompt_id"]

                    # Record in database
                    conn = psycopg2.connect(**self.db_config)
                    cursor = conn.cursor()

                    cursor.execute("""
                        INSERT INTO scene_generations
                        (episode_id, scene_number, prompt_id, scene_type, description, status)
                        VALUES (%s, %s, %s, %s, %s, 'generating')
                    """, (episode_id, scene_number, prompt_id, scene_type, description))

                    conn.commit()
                    conn.close()

                    return {
                        "episode_id": episode_id,
                        "scene_number": scene_number,
                        "prompt_id": prompt_id,
                        "status": "generating"
                    }
                else:
                    return {
                        "error": "Failed to submit generation",
                        "status_code": response.status
                    }

    async def batch_produce_episode(self, episode_id: int):
        """Produce all scenes for an entire episode"""

        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()

        # Get episode scenes
        cursor.execute("""
            SELECT scene_number, scene_type, characters, description
            FROM episode_scenes
            WHERE episode_id = %s
            ORDER BY scene_number
        """, (episode_id,))

        scenes = cursor.fetchall()
        conn.close()

        results = []

        for scene_number, scene_type, characters, description in scenes:
            character_list = json.loads(characters) if characters else []

            result = await self.produce_episode_scene(
                episode_id,
                scene_number,
                scene_type,
                character_list,
                description
            )

            results.append(result)

            # Add delay between scenes to avoid overload
            await asyncio.sleep(5)

        return {
            "episode_id": episode_id,
            "total_scenes": len(results),
            "scenes": results
        }

    def create_database_schema(self):
        """Create necessary database tables"""

        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()

        # Episode scenes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS episode_scenes (
                id SERIAL PRIMARY KEY,
                episode_id INTEGER,
                scene_number INTEGER,
                scene_type VARCHAR(50),
                characters JSONB,
                description TEXT,
                duration_seconds FLOAT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Scene generations tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scene_generations (
                id SERIAL PRIMARY KEY,
                episode_id INTEGER,
                scene_number INTEGER,
                prompt_id VARCHAR(255),
                scene_type VARCHAR(50),
                description TEXT,
                status VARCHAR(50),
                output_path TEXT,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

        logger.info("Database schema created")


async def main():
    """Demonstrate the production manager"""

    manager = AnimeProductionManager()
    manager.create_database_schema()

    # Example: Generate character reference sheet
    references = await manager.generate_character_reference_sheet("Mei Kobayashi")
    print(f"Generated references: {references}")

    # Example: Produce a scene
    scene = await manager.produce_episode_scene(
        episode_id=1,
        scene_number=1,
        scene_type="action_fight",
        character_names=["Mei Kobayashi"],
        description="Mei fighting against multiple opponents in a warehouse"
    )
    print(f"Scene generation started: {scene}")


if __name__ == "__main__":
    asyncio.run(main())