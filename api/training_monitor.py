#!/usr/bin/env python3
"""
Training Monitor - Tracks LoRA training status and auto-deployment
"""

import asyncio
from pathlib import Path
import shutil
import subprocess
from datetime import datetime
import json
from typing import Dict, List, Optional

LORA_OUTPUT_DIR = Path("/mnt/1TB-storage/lora_output")
COMFYUI_LORA_DIR = Path("/mnt/1TB-storage/models/loras")
TRAINING_DIR = Path("/mnt/1TB-storage/lora_training")

async def check_training_status(character_name: str) -> dict:
    """Check if training is running and what outputs exist"""

    # Find training directories for this character
    training_dirs = list(TRAINING_DIR.glob(f"{character_name}_*"))
    output_dirs = list(LORA_OUTPUT_DIR.glob(f"{character_name}_*"))

    # Check if training process is running
    result = subprocess.run(
        ["pgrep", "-f", f"train_network.*{character_name}"],
        capture_output=True,
        text=True
    )
    is_training = result.returncode == 0

    # Find completed LoRAs
    completed_loras = []
    for output_dir in output_dirs:
        if not output_dir.is_dir():
            continue

        loras = list(output_dir.glob("*.safetensors"))
        for lora in loras:
            completed_loras.append({
                "path": str(lora),
                "size_mb": lora.stat().st_size / 1024 / 1024,
                "created": datetime.fromtimestamp(lora.stat().st_mtime).isoformat()
            })

    # Sort by creation time, latest first
    completed_loras.sort(key=lambda x: x["created"], reverse=True)

    # Check if deployed to ComfyUI
    deployed_to_comfyui = (COMFYUI_LORA_DIR / f"{character_name}_lora.safetensors").exists()

    return {
        "character_name": character_name,
        "is_training": is_training,
        "training_dirs": [str(d) for d in training_dirs],
        "completed_loras": completed_loras,
        "deployed_to_comfyui": deployed_to_comfyui,
        "latest_lora": completed_loras[0] if completed_loras else None
    }

async def deploy_lora_to_comfyui(lora_path: str, character_name: str) -> dict:
    """Copy trained LoRA to ComfyUI models folder"""

    src = Path(lora_path)
    if not src.exists():
        raise FileNotFoundError(f"LoRA not found: {lora_path}")

    # Copy to ComfyUI loras folder with standardized name
    dst = COMFYUI_LORA_DIR / f"{character_name}_lora.safetensors"

    # Ensure directory exists
    dst.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy(src, dst)

    return {
        "deployed": True,
        "source": str(src),
        "destination": str(dst),
        "size_mb": dst.stat().st_size / 1024 / 1024,
        "deployed_at": datetime.now().isoformat()
    }

async def auto_deploy_completed_loras() -> List[dict]:
    """Find all completed LoRAs and deploy to ComfyUI"""

    deployed = []

    if not LORA_OUTPUT_DIR.exists():
        return deployed

    for output_dir in LORA_OUTPUT_DIR.iterdir():
        if not output_dir.is_dir():
            continue

        # Extract character name from directory name
        character_name = output_dir.name.split("_")[0]

        # Find latest LoRA file in this directory
        lora_files = list(output_dir.glob("*.safetensors"))
        if not lora_files:
            continue

        # Get the latest file by modification time
        latest_lora = max(lora_files, key=lambda f: f.stat().st_mtime)

        # Check if already deployed
        dst = COMFYUI_LORA_DIR / f"{character_name}_lora.safetensors"
        if not dst.exists() or dst.stat().st_mtime < latest_lora.stat().st_mtime:
            try:
                result = await deploy_lora_to_comfyui(str(latest_lora), character_name)
                deployed.append({
                    "character": character_name,
                    "source": str(latest_lora),
                    "destination": str(dst),
                    "result": result
                })
            except Exception as e:
                deployed.append({
                    "character": character_name,
                    "error": str(e)
                })

    return deployed

async def get_all_characters() -> List[str]:
    """Get all character names that have training or output directories"""
    characters = set()

    # From training directories
    if TRAINING_DIR.exists():
        for d in TRAINING_DIR.iterdir():
            if d.is_dir():
                characters.add(d.name.split("_")[0])

    # From output directories
    if LORA_OUTPUT_DIR.exists():
        for d in LORA_OUTPUT_DIR.iterdir():
            if d.is_dir():
                characters.add(d.name.split("_")[0])

    return sorted(list(characters))

async def get_training_progress(character_name: str) -> Optional[dict]:
    """Try to extract training progress from log files"""

    training_dirs = list(TRAINING_DIR.glob(f"{character_name}_*"))
    if not training_dirs:
        return None

    # Look for log files or training scripts that might contain progress info
    latest_dir = max(training_dirs, key=lambda d: d.stat().st_mtime)

    # Check for any log files
    log_files = list(latest_dir.glob("*.log"))
    if not log_files:
        # Look for systemwide training logs
        log_files = list(Path("/tmp").glob(f"*{character_name}*.log"))

    if log_files:
        latest_log = max(log_files, key=lambda f: f.stat().st_mtime)
        try:
            with open(latest_log, 'r') as f:
                lines = f.readlines()[-50:]  # Last 50 lines

            # Try to extract epoch information
            current_epoch = None
            total_epochs = None

            for line in lines:
                if "epoch" in line.lower():
                    # Simple regex to find epoch numbers
                    import re
                    match = re.search(r'epoch[:\s]+(\d+)[/\s]*(\d+)?', line.lower())
                    if match:
                        current_epoch = int(match.group(1))
                        if match.group(2):
                            total_epochs = int(match.group(2))

            if current_epoch is not None:
                progress = (current_epoch / total_epochs * 100) if total_epochs else current_epoch * 10
                return {
                    "current_epoch": current_epoch,
                    "total_epochs": total_epochs,
                    "progress_percent": min(progress, 100),
                    "log_file": str(latest_log)
                }
        except Exception as e:
            print(f"Error reading log file: {e}")

    return None

if __name__ == "__main__":
    import sys

    async def main():
        if len(sys.argv) < 2:
            print("Usage: python training_monitor.py <command> [args]")
            print("Commands:")
            print("  status <character_name>  - Check training status for character")
            print("  status_all               - Check all characters")
            print("  deploy <character_name>  - Deploy latest LoRA for character")
            print("  auto_deploy              - Auto-deploy all completed LoRAs")
            return

        command = sys.argv[1]

        if command == "status" and len(sys.argv) == 3:
            character = sys.argv[2]
            status = await check_training_status(character)
            print(json.dumps(status, indent=2))

        elif command == "status_all":
            characters = await get_all_characters()
            all_status = {}
            for char in characters:
                all_status[char] = await check_training_status(char)
            print(json.dumps(all_status, indent=2))

        elif command == "deploy" and len(sys.argv) == 3:
            character = sys.argv[2]
            status = await check_training_status(character)
            if not status["completed_loras"]:
                print(f"No completed LoRA found for {character}")
                return

            latest = status["latest_lora"]
            result = await deploy_lora_to_comfyui(latest["path"], character)
            print(json.dumps(result, indent=2))

        elif command == "auto_deploy":
            deployed = await auto_deploy_completed_loras()
            print(json.dumps(deployed, indent=2))

        else:
            print("Invalid command")

    asyncio.run(main())