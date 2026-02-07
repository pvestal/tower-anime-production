#!/usr/bin/env python3
"""
Training Dataset Builder
Builds LoRA training datasets from verified character references
"""

import json
import shutil
import asyncio
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import asyncpg
import aiohttp
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

router = APIRouter()

class TrainingConfig(BaseModel):
    character_name: str
    project_id: int
    min_images: int = 10
    max_images: int = 50
    include_youtube_frames: bool = True
    use_existing_lora_images: bool = True

class TrainingJob(BaseModel):
    job_id: str
    character_name: str
    project_id: int
    status: str
    dataset_path: str
    image_count: int
    started_at: datetime

async def get_db():
    """Get database connection"""
    return await asyncpg.connect(
        host='localhost',
        port=5432,
        user='patrick',
        password='RP78eIrW7cI2jYvL5akt1yurE',
        database='anime_production'
    )

async def build_training_dataset(config: TrainingConfig) -> Dict[str, Any]:
    """Build LoRA training dataset from verified references"""

    character_name = config.character_name.lower().replace(' ', '_')

    # Use existing LoRA dataset images as our verified references
    source_dirs = []

    if config.use_existing_lora_images:
        # Check for existing clean images
        clean_dir = Path(f"/mnt/1TB-storage/lora_datasets/clean_mario_galaxy_{character_name}/images")
        if clean_dir.exists():
            source_dirs.append(clean_dir)

        # Check for regular dataset
        regular_dir = Path(f"/mnt/1TB-storage/lora_datasets/mario_galaxy_{character_name}/images")
        if regular_dir.exists():
            source_dirs.append(regular_dir)

    # Check for YouTube extracted frames
    if config.include_youtube_frames:
        frames_dir = Path(f"/mnt/1TB-storage/training_videos/mario_galaxy/character_analysis/{character_name}")
        if frames_dir.exists():
            source_dirs.append(frames_dir)

    # Collect all available images
    all_images = []
    for source_dir in source_dirs:
        for img_path in source_dir.glob("*.png"):
            all_images.append(img_path)
        for img_path in source_dir.glob("*.jpg"):
            all_images.append(img_path)

    if len(all_images) < config.min_images:
        raise ValueError(f"Need {config.min_images}+ images, found {len(all_images)}")

    # Use LoRA Studio dataset directory structure
    dataset_dir = Path(f"/mnt/1TB-storage/datasets/characters/{character_name}")
    images_dir = dataset_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # Also create backup timestamp directory for training
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    training_dir = Path(f"/mnt/1TB-storage/lora_training/{character_name}_{timestamp}")
    training_images_dir = training_dir / "images"
    training_images_dir.mkdir(parents=True, exist_ok=True)

    # Copy images and create captions
    selected_images = all_images[:config.max_images]

    # Character-specific captions based on movie style
    caption_templates = {
        "bowser_jr": "Bowser Jr, Illumination Studios 3D movie style, small koopa villain, orange spiky mohawk, RED BLOODSHOT EYES, sharp teeth, green spiked shell, white bib with angry mouth drawing",
        "mario": "Mario, Illumination Studios 3D movie style, red cap with M logo, blue overalls, brown mustache, white gloves, friendly expression",
        "luigi": "Luigi, Illumination Studios 3D movie style, green cap with L logo, blue overalls, brown mustache, tall and lanky, nervous expression",
        "princess_peach": "Princess Peach, Illumination Studios 3D movie style, pink dress, blonde hair, blue eyes, crown, elegant pose",
        "rosalina": "Rosalina, Illumination Studios 3D movie style, cyan dress, platinum blonde hair covering one eye, tall elegant figure, star wand"
    }

    base_caption = caption_templates.get(character_name, f"{character_name}, 3D movie style character")

    for i, img_path in enumerate(selected_images):
        # Copy image to both locations
        dst_path = images_dir / f"{character_name}_{i:04d}{img_path.suffix}"
        training_dst_path = training_images_dir / f"{character_name}_{i:04d}{img_path.suffix}"

        shutil.copy(img_path, dst_path)
        shutil.copy(img_path, training_dst_path)

        # Create caption file with movie-accurate description
        caption = f"{base_caption}, high quality, professional 3D render"
        caption_file = images_dir / f"{character_name}_{i:04d}.txt"
        training_caption_file = training_images_dir / f"{character_name}_{i:04d}.txt"

        caption_file.write_text(caption)
        training_caption_file.write_text(caption)

    # Create dataset configuration for kohya
    dataset_config = {
        "dataset": {
            "subsets": [
                {
                    "image_dir": str(images_dir),
                    "class_tokens": character_name,
                    "num_repeats": 10,
                    "is_reg": False
                }
            ]
        },
        "train": {
            "batch_size": 1,
            "resolution": 512,
            "max_train_epochs": 10,
            "save_every_n_epochs": 2,
            "caption_extension": ".txt"
        }
    }

    config_path = dataset_dir / "dataset_config.json"
    config_path.write_text(json.dumps(dataset_config, indent=2))

    return {
        "dataset_path": str(dataset_dir),
        "training_path": str(training_dir),
        "image_count": len(selected_images),
        "config_path": str(config_path),
        "character_name": character_name,
        "timestamp": timestamp
    }

@router.post("/api/training/build_dataset")
async def build_dataset_endpoint(config: TrainingConfig):
    """Build training dataset from references"""
    try:
        result = await build_training_dataset(config)
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/training/start/{character_name}")
async def start_training(character_name: str, project_id: int = 41, background_tasks: BackgroundTasks = None):
    """Start LoRA training for a character"""

    # Build dataset first
    config = TrainingConfig(
        character_name=character_name,
        project_id=project_id,
        min_images=5,  # Lower threshold for testing
        max_images=20
    )

    try:
        dataset_info = await build_training_dataset(config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Connect to LoRA training system
    training_request = {
        "character_name": character_name,
        "dataset_path": dataset_info["dataset_path"],
        "config_path": dataset_info["config_path"],
        "output_dir": f"/mnt/1TB-storage/lora_output/{character_name}_{dataset_info['timestamp']}",
        "model_name": f"{character_name}_lora",
        "training_params": {
            "learning_rate": 0.0001,
            "train_batch_size": 1,
            "max_train_steps": 1000,
            "save_steps": 250,
            "mixed_precision": "fp16"
        }
    }

    # Call LoRA Studio's training system directly
    try:
        # Use LoRA Studio's training system
        import subprocess
        import sys
        lora_studio_script = "/opt/tower-lora-studio/train_character.py"

        # Run the LoRA Studio training system
        result = subprocess.run(
            [sys.executable, lora_studio_script],
            cwd="/opt/tower-lora-studio",
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            return {
                "success": True,
                "message": f"LoRA Studio training initiated for {character_name}",
                "dataset_info": dataset_info,
                "lora_studio_output": result.stdout
            }
        else:
            print(f"LoRA Studio error: {result.stderr}")
            # Fall back to manual Kohya training

    except Exception as e:
        print(f"Failed to call LoRA Studio: {e}")
        # Fall back to manual training

    # Fallback: Create training script
    training_script = f"""#!/bin/bash
# LoRA Training Script for {character_name}
# Generated at {datetime.now()}

cd /opt/kohya_ss

accelerate launch train_network.py \\
    --pretrained_model_name_or_path="/mnt/1TB-storage/models/checkpoints/animagine-xl-3.1.safetensors" \\
    --dataset_config="{dataset_info['config_path']}" \\
    --output_dir="/mnt/1TB-storage/lora_output/{character_name}_{dataset_info['timestamp']}" \\
    --output_name="{character_name}_lora" \\
    --save_model_as=safetensors \\
    --prior_loss_weight=1.0 \\
    --max_train_steps=1000 \\
    --learning_rate=1e-4 \\
    --optimizer_type="AdamW8bit" \\
    --xformers \\
    --mixed_precision="fp16" \\
    --cache_latents \\
    --gradient_checkpointing \\
    --save_every_n_steps=250
"""

    script_path = Path(dataset_info["dataset_path"]) / "train.sh"
    script_path.write_text(training_script)
    script_path.chmod(0o755)

    return {
        "success": True,
        "message": f"Training dataset prepared for {character_name}",
        "dataset_info": dataset_info,
        "training_script": str(script_path),
        "note": "Run the training script manually or start the LoRA training service"
    }

@router.get("/api/training/status/{character_name}")
async def get_training_status(character_name: str):
    """Get training status for a character"""

    character_name = character_name.lower().replace(' ', '_')

    # Check for existing datasets
    training_dir = Path(f"/mnt/1TB-storage/lora_training")
    datasets = list(training_dir.glob(f"{character_name}_*"))

    # Check for output LoRAs
    output_dir = Path(f"/mnt/1TB-storage/lora_output")
    loras = list(output_dir.glob(f"{character_name}_*/"))

    # Check existing clean images
    clean_images = Path(f"/mnt/1TB-storage/lora_datasets/clean_mario_galaxy_{character_name}/images")
    image_count = len(list(clean_images.glob("*.png"))) if clean_images.exists() else 0

    return {
        "character_name": character_name,
        "available_images": image_count,
        "datasets_created": len(datasets),
        "loras_trained": len(loras),
        "ready_for_training": image_count >= 5,
        "latest_dataset": str(datasets[-1]) if datasets else None,
        "latest_lora": str(loras[-1]) if loras else None
    }

@router.get("/api/training/characters")
async def list_trainable_characters():
    """List all characters with enough data for training"""

    characters = ["mario", "luigi", "bowser_jr", "princess_peach", "rosalina"]
    trainable = []

    for char in characters:
        status = await get_training_status(char)
        if status["ready_for_training"]:
            trainable.append({
                "name": char,
                "display_name": char.replace('_', ' ').title(),
                "image_count": status["available_images"],
                "has_trained_lora": status["loras_trained"] > 0
            })

    return trainable

if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI

    app = FastAPI(title="Training Dataset Builder")
    app.include_router(router)

    uvicorn.run(app, host="0.0.0.0", port=8408)