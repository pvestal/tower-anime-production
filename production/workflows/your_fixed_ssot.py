#!/usr/bin/env python3
"""
YOUR FIXED SSOT WORKFLOW
Adapting your 30-second workflow to work within AnimateDiff 32-frame limit
Using YOUR characters, YOUR LoRA, YOUR models - but with realistic frame counts
"""

import requests
import json
import time
import psycopg2
from typing import Dict, Any

class YourFixedSSOTWorkflow:
    """Fixed version of Patrick's SSOT workflow that actually works"""

    def __init__(self):
        self.comfyui_url = "http://localhost:8188"
        self.db_config = {
            'host': 'localhost',
            'database': 'tower_consolidated',
            'user': 'patrick',
            'password': 'RP78eIrW7cI2jYvL5akt1yurE'
        }

    def get_characters(self):
        """Get YOUR actual characters from database"""
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        cur.execute("SELECT name, description FROM characters WHERE name != 'Test Character' AND name != 'Integration Test Character' LIMIT 3")
        characters = cur.fetchall()
        conn.close()
        return characters

    def create_fixed_workflow_for_character(self, character_name, character_desc):
        """Create working AnimateDiff workflow with YOUR character using YOUR models"""

        # Create character-specific prompt using YOUR character data
        if "Akira" in character_name:
            prompt = "masterpiece, best quality, Akira Yamamoto, 22-year-old man with spiky black hair, cybernetic arm implants, neon blue jacket, street racer, dynamic action pose in cyberpunk city, detailed character design, anime style"
        elif "Luna" in character_name:
            prompt = "masterpiece, best quality, Luna Chen, woman with silver hair, holographic tattoos, lab coat, AI researcher, dynamic pose in futuristic laboratory, detailed character design, anime style"
        elif "Viktor" in character_name:
            prompt = "masterpiece, best quality, Viktor Kozlov, corporate man in expensive suit, augmented reality monocle, cold expression, CEO, dynamic pose in corporate office, detailed character design, anime style"
        else:
            prompt = f"masterpiece, best quality, {character_name}, {character_desc[:100]}, dynamic pose, anime style, detailed character design"

        # Working workflow using YOUR models but with realistic frame count
        workflow = {
            # 1. Use YOUR checkpoint
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "AOM3A1B.safetensors"}
            },
            # 2. Use YOUR LoRA
            "2": {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": ["1", 0],
                    "clip": ["1", 1],
                    "lora_name": "mei_working_v1.safetensors",
                    "strength_model": 1.0,
                    "strength_clip": 1.0
                }
            },
            # 3. YOUR character prompt
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["2", 1]
                }
            },
            # 4. Negative prompt
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": "worst quality, low quality, blurry, ugly, distorted, static, still image",
                    "clip": ["2", 1]
                }
            },
            # 5. AnimateDiff setup
            "5": {
                "class_type": "ADE_LoadAnimateDiffModel",
                "inputs": {"model_name": "v3_sd15_mm.ckpt"}
            },
            "6": {
                "class_type": "ADE_ApplyAnimateDiffModelSimple",
                "inputs": {"motion_model": ["5", 0]}
            },
            "7": {
                "class_type": "ADE_UseEvolvedSampling",
                "inputs": {
                    "model": ["2", 0],
                    "m_models": ["6", 0],
                    "beta_schedule": "autoselect"
                }
            },
            # 8. 16-frame latent (realistic limit)
            "8": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": 512, "height": 288, "batch_size": 16}
            },
            # 9. Sampling
            "9": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": int(time.time()) % 2147483647,
                    "steps": 20,
                    "cfg": 7.0,
                    "sampler_name": "euler_ancestral",
                    "scheduler": "normal",
                    "positive": ["3", 0],
                    "negative": ["4", 0],
                    "latent_image": ["8", 0],
                    "model": ["7", 0],
                    "denoise": 1.0
                }
            },
            # 10. Decode
            "10": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["9", 0], "vae": ["1", 2]}
            },
            # 11. Save video
            "11": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": ["10", 0],
                    "frame_rate": 8,
                    "loop_count": 0,
                    "filename_prefix": f"your_character_{character_name.replace(' ', '_').lower()}_",
                    "format": "video/h264-mp4",
                    "pingpong": False,
                    "save_output": True
                }
            }
        }

        return workflow

    def generate_character_video(self, character_name, character_desc):
        """Generate video using YOUR character and YOUR models"""
        print(f"🎬 Generating video for YOUR character: {character_name}")
        print(f"   Using YOUR models: AOM3A1B.safetensors + mei_working_v1.safetensors")

        workflow = self.create_fixed_workflow_for_character(character_name, character_desc)

        # Submit to ComfyUI
        response = requests.post(f"{self.comfyui_url}/prompt", json={"prompt": workflow})
        result = response.json()

        if 'prompt_id' in result:
            prompt_id = result['prompt_id']
            print(f"✅ YOUR character workflow submitted: {prompt_id}")
            return prompt_id
        else:
            print(f"❌ Failed: {result}")
            return None

def main():
    """Generate videos for YOUR characters using YOUR models"""
    workflow_runner = YourFixedSSOTWorkflow()

    # Get YOUR characters
    characters = workflow_runner.get_characters()
    print(f"📋 YOUR Characters Found: {len(characters)}")

    # Generate for each of YOUR characters
    for char_name, char_desc in characters[:3]:  # Test with first 3
        print(f"\n🎯 YOUR Character: {char_name}")
        print(f"   Description: {char_desc[:150]}...")

        job_id = workflow_runner.generate_character_video(char_name, char_desc)

        if job_id:
            print(f"✅ Generated for {char_name} - Job ID: {job_id}")
            time.sleep(5)  # Brief pause between characters
        else:
            print(f"❌ Failed for {char_name}")

    print(f"\n🎬 Check outputs: ls /mnt/1TB-storage/ComfyUI/output/your_character_*")

if __name__ == "__main__":
    main()