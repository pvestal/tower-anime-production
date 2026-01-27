#!/usr/bin/env python3
"""
Anime Production LoRA Pipeline
Integrated system for training and managing character/action LoRAs
"""

import os
import json
import subprocess
import psycopg2
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging
import hashlib
import shutil

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnimeLoRAPipeline:
    """Complete LoRA training and management system for anime production"""

    def __init__(self):
        self.base_dir = Path("/opt/tower-lora-studio")
        self.ai_toolkit_dir = self.base_dir / "ai-toolkit"
        self.training_data_dir = Path("/mnt/1TB-storage/anime_training_data")
        self.lora_output_dir = Path("/mnt/1TB-storage/models/loras/anime_production")

        # Database connection
        self.db_config = {
            "host": "localhost",
            "database": "anime_production",
            "user": "patrick",
            "password": "RP78eIrW7cI2jYvL5akt1yurE"
        }

        # Training presets for different types
        self.training_presets = {
            "character": {
                "steps": 1500,
                "rank": 32,
                "alpha": 16,
                "learning_rate": 1e-4,
                "batch_size": 1,
                "gradient_accumulation": 4,
                "resolution": "768x512"
            },
            "action": {
                "steps": 1000,
                "rank": 16,
                "alpha": 8,
                "learning_rate": 5e-5,
                "batch_size": 1,
                "gradient_accumulation": 2,
                "resolution": "512x384"
            },
            "style": {
                "steps": 800,
                "rank": 8,
                "alpha": 4,
                "learning_rate": 1e-5,
                "batch_size": 1,
                "gradient_accumulation": 2,
                "resolution": "512x384"
            }
        }

        # Ensure directories exist
        self.training_data_dir.mkdir(parents=True, exist_ok=True)
        self.lora_output_dir.mkdir(parents=True, exist_ok=True)

    def init_database(self):
        """Create database tables for LoRA management"""

        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()

        # LoRA registry table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lora_models (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL,
                type VARCHAR(50) NOT NULL, -- character, action, style, nsfw
                trigger_word VARCHAR(100) NOT NULL,
                file_path TEXT NOT NULL,
                model_hash VARCHAR(64),
                training_config JSONB,
                training_data_path TEXT,
                base_model VARCHAR(100) DEFAULT 'ltxv-2b-fp8',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata JSONB
            )
        """)

        # Training jobs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lora_training_jobs (
                id SERIAL PRIMARY KEY,
                lora_id INTEGER REFERENCES lora_models(id),
                status VARCHAR(50) DEFAULT 'pending', -- pending, training, completed, failed
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                training_params JSONB,
                error_message TEXT,
                output_path TEXT
            )
        """)

        # LoRA combinations for scenes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scene_lora_configs (
                id SERIAL PRIMARY KEY,
                scene_id INTEGER,
                character_lora_id INTEGER REFERENCES lora_models(id),
                action_lora_id INTEGER REFERENCES lora_models(id),
                style_lora_id INTEGER REFERENCES lora_models(id),
                character_strength FLOAT DEFAULT 1.0,
                action_strength FLOAT DEFAULT 0.8,
                style_strength FLOAT DEFAULT 0.5,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

        logger.info("Database tables initialized")

    def prepare_character_training_data(self, character_name: str, source_videos: List[Path]) -> Path:
        """Extract and prepare frames for character training"""

        character_dir = self.training_data_dir / f"character_{character_name.lower().replace(' ', '_')}"
        character_dir.mkdir(parents=True, exist_ok=True)

        frames_dir = character_dir / "frames"
        frames_dir.mkdir(exist_ok=True)

        logger.info(f"Preparing training data for {character_name}")

        frame_count = 0
        for video_path in source_videos:
            if not video_path.exists():
                continue

            # Extract 10 frames per video at different timestamps
            for i in range(10):
                timestamp = i * 2.5  # Extract every 2.5 seconds
                frame_path = frames_dir / f"frame_{frame_count:04d}.png"

                cmd = [
                    "ffmpeg", "-ss", str(timestamp),
                    "-i", str(video_path),
                    "-vframes", "1",
                    "-vf", "scale=768:512",
                    str(frame_path),
                    "-y"
                ]

                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    # Create caption file
                    caption = f"{character_name.lower().replace(' ', '_')}, anime character, detailed"
                    caption_path = frame_path.with_suffix('.txt')
                    caption_path.write_text(caption)
                    frame_count += 1

        logger.info(f"Extracted {frame_count} frames for {character_name}")

        # Create metadata file
        metadata = {
            "character_name": character_name,
            "trigger_word": character_name.lower().replace(' ', '_'),
            "num_frames": frame_count,
            "resolution": "768x512",
            "prepared_at": datetime.now().isoformat()
        }

        metadata_path = character_dir / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        return character_dir

    def create_training_config(self,
                              lora_name: str,
                              lora_type: str,
                              trigger_word: str,
                              training_data_path: Path) -> Path:
        """Create ai-toolkit training configuration"""

        preset = self.training_presets.get(lora_type, self.training_presets["action"])

        config = {
            "job": "extension",
            "config": {
                "name": lora_name,
                "process": [
                    {
                        "type": "ltx_video_lora",
                        "training_folder": str(training_data_path),
                        "output_dir": str(self.lora_output_dir),
                        "trigger_word": trigger_word,

                        # Model settings
                        "base_model": "ltxv-2b-fp8",
                        "model_path": "/mnt/1TB-storage/ComfyUI/models/checkpoints/ltxv-2b-fp8.safetensors",

                        # Training parameters
                        "steps": preset["steps"],
                        "rank": preset["rank"],
                        "alpha": preset["alpha"],
                        "learning_rate": preset["learning_rate"],
                        "batch_size": preset["batch_size"],
                        "gradient_accumulation_steps": preset["gradient_accumulation"],

                        # Resolution
                        "resolution": preset["resolution"],

                        # Optimization
                        "mixed_precision": "fp16",
                        "gradient_checkpointing": True,
                        "xformers": True,
                        "cache_latents": True,

                        # Saving
                        "save_every": 250,
                        "sample_every": 100,
                        "sample_prompts": [
                            f"{trigger_word}, high quality",
                            f"{trigger_word}, action scene",
                            f"{trigger_word}, close-up portrait"
                        ]
                    }
                ]
            }
        }

        config_path = self.base_dir / f"configs/{lora_name}_config.json"
        config_path.parent.mkdir(exist_ok=True)

        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        return config_path

    def train_lora(self,
                   lora_name: str,
                   lora_type: str,
                   trigger_word: str,
                   training_data_path: Path) -> Optional[Path]:
        """Execute LoRA training using ai-toolkit"""

        # Create config
        config_path = self.create_training_config(
            lora_name, lora_type, trigger_word, training_data_path
        )

        # Record in database
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()

        # Insert LoRA record
        cursor.execute("""
            INSERT INTO lora_models (name, type, trigger_word, file_path, training_data_path, training_config)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE
            SET updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """, (
            lora_name,
            lora_type,
            trigger_word,
            str(self.lora_output_dir / f"{lora_name}.safetensors"),
            str(training_data_path),
            json.dumps(self.training_presets[lora_type])
        ))

        lora_id = cursor.fetchone()[0]

        # Create training job
        cursor.execute("""
            INSERT INTO lora_training_jobs (lora_id, status, started_at, training_params)
            VALUES (%s, 'training', CURRENT_TIMESTAMP, %s)
            RETURNING id
        """, (lora_id, json.dumps(self.training_presets[lora_type])))

        job_id = cursor.fetchone()[0]
        conn.commit()

        logger.info(f"Starting training job {job_id} for {lora_name}")

        # Run training
        cmd = [
            "python3", str(self.ai_toolkit_dir / "run.py"),
            str(config_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.ai_toolkit_dir),
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )

            if result.returncode == 0:
                # Update job status
                output_path = self.lora_output_dir / f"{lora_name}.safetensors"

                cursor.execute("""
                    UPDATE lora_training_jobs
                    SET status = 'completed',
                        completed_at = CURRENT_TIMESTAMP,
                        output_path = %s
                    WHERE id = %s
                """, (str(output_path), job_id))

                # Calculate model hash
                if output_path.exists():
                    with open(output_path, 'rb') as f:
                        model_hash = hashlib.sha256(f.read()).hexdigest()

                    cursor.execute("""
                        UPDATE lora_models
                        SET model_hash = %s
                        WHERE id = %s
                    """, (model_hash, lora_id))

                    # Copy to ComfyUI
                    comfyui_path = Path("/mnt/1TB-storage/ComfyUI/models/loras") / output_path.name
                    shutil.copy2(output_path, comfyui_path)

                    logger.info(f"Training completed: {output_path}")
                    conn.commit()
                    conn.close()
                    return output_path
            else:
                raise Exception(f"Training failed: {result.stderr}")

        except Exception as e:
            # Update job with error
            cursor.execute("""
                UPDATE lora_training_jobs
                SET status = 'failed',
                    completed_at = CURRENT_TIMESTAMP,
                    error_message = %s
                WHERE id = %s
            """, (str(e), job_id))
            conn.commit()
            conn.close()

            logger.error(f"Training failed: {e}")
            return None

    def create_scene_generation(self,
                               scene_description: str,
                               character_lora: Optional[str] = None,
                               action_lora: Optional[str] = None,
                               style_lora: Optional[str] = None) -> Dict:
        """Create a generation workflow with multiple LoRAs"""

        workflow = {
            "checkpoint": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "ltxv-2b-fp8.safetensors"}
            },
            "clip": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": "t5xxl_fp16.safetensors", "type": "ltxv"}
            }
        }

        # Chain LoRAs
        prev_model = ["checkpoint", 0]
        prev_clip = ["clip", 0]
        lora_count = 0

        if character_lora:
            lora_count += 1
            workflow[f"lora_{lora_count}"] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": character_lora,
                    "strength_model": 1.0,
                    "strength_clip": 1.0,
                    "model": prev_model,
                    "clip": prev_clip
                }
            }
            prev_model = [f"lora_{lora_count}", 0]
            prev_clip = [f"lora_{lora_count}", 1]

        if action_lora:
            lora_count += 1
            workflow[f"lora_{lora_count}"] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": action_lora,
                    "strength_model": 0.8,
                    "strength_clip": 0.8,
                    "model": prev_model,
                    "clip": prev_clip
                }
            }
            prev_model = [f"lora_{lora_count}", 0]
            prev_clip = [f"lora_{lora_count}", 1]

        if style_lora:
            lora_count += 1
            workflow[f"lora_{lora_count}"] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": style_lora,
                    "strength_model": 0.5,
                    "strength_clip": 0.5,
                    "model": prev_model,
                    "clip": prev_clip
                }
            }
            prev_model = [f"lora_{lora_count}", 0]
            prev_clip = [f"lora_{lora_count}", 1]

        # Add generation nodes
        workflow.update({
            "positive": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": scene_description, "clip": prev_clip}
            },
            "negative": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "low quality, blurry", "clip": prev_clip}
            },
            "latent": {
                "class_type": "EmptyLTXVLatentVideo",
                "inputs": {"width": 768, "height": 512, "length": 49, "batch_size": 1}
            },
            "conditioning": {
                "class_type": "LTXVConditioning",
                "inputs": {
                    "positive": ["positive", 0],
                    "negative": ["negative", 0],
                    "frame_rate": 24
                }
            },
            "sample": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": int(datetime.now().timestamp()),
                    "steps": 20,
                    "cfg": 4.5,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "denoise": 1.0,
                    "model": prev_model,
                    "positive": ["conditioning", 0],
                    "negative": ["conditioning", 1],
                    "latent_image": ["latent", 0]
                }
            },
            "decode": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["sample", 0],
                    "vae": ["checkpoint", 2]
                }
            },
            "save": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": ["decode", 0],
                    "frame_rate": 24,
                    "loop_count": 0,
                    "filename_prefix": f"anime_scene_{int(datetime.now().timestamp())}",
                    "format": "video/h264-mp4",
                    "pingpong": False,
                    "save_output": True
                }
            }
        })

        return workflow

    def batch_generate_episode_scenes(self, episode_id: int):
        """Generate all scenes for an episode using appropriate LoRAs"""

        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()

        # Get scenes for episode
        cursor.execute("""
            SELECT id, description, character_id, action_type
            FROM scenes
            WHERE episode_id = %s
            ORDER BY scene_number
        """, (episode_id,))

        scenes = cursor.fetchall()

        for scene_id, description, character_id, action_type in scenes:
            # Get appropriate LoRAs
            cursor.execute("""
                SELECT name FROM lora_models
                WHERE type = 'character' AND metadata->>'character_id' = %s
            """, (str(character_id),))

            character_lora = cursor.fetchone()
            character_lora = character_lora[0] if character_lora else None

            # Get action LoRA based on type
            action_lora = None
            if action_type:
                cursor.execute("""
                    SELECT name FROM lora_models
                    WHERE type = 'action' AND trigger_word = %s
                """, (action_type,))
                result = cursor.fetchone()
                action_lora = result[0] if result else None

            # Generate scene
            workflow = self.create_scene_generation(
                description,
                character_lora=character_lora,
                action_lora=action_lora
            )

            # Submit to ComfyUI
            import requests
            response = requests.post(
                "http://localhost:8188/prompt",
                json={"prompt": workflow}
            )

            if response.status_code == 200:
                prompt_id = response.json()["prompt_id"]
                logger.info(f"Generating scene {scene_id}: {prompt_id}")
            else:
                logger.error(f"Failed to generate scene {scene_id}")

        conn.close()


def main():
    """Initialize and demonstrate the anime LoRA pipeline"""

    pipeline = AnimeLoRAPipeline()

    # Initialize database
    pipeline.init_database()

    logger.info("Anime LoRA Pipeline initialized")
    logger.info(f"Training data: {pipeline.training_data_dir}")
    logger.info(f"Output LoRAs: {pipeline.lora_output_dir}")

    # Example: Train a character LoRA
    # videos = list(Path("/mnt/1TB-storage/ComfyUI/output").glob("*mei*.mp4"))
    # if videos:
    #     data_path = pipeline.prepare_character_training_data("Mei Kobayashi", videos[:3])
    #     pipeline.train_lora("mei_kobayashi_v1", "character", "mei", data_path)


if __name__ == "__main__":
    main()