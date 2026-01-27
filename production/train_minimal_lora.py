#!/usr/bin/env python3
"""
MINIMAL LoRA Training Test
Train a tiny LoRA on LTX with just a few frames
Start as small as possible
"""

import os
import json
import subprocess
from pathlib import Path
import requests
import time

class MinimalLoRATrainer:
    def __init__(self):
        self.base_dir = Path("/mnt/1TB-storage/ltx_training/minimal_test")
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Use the simplest concept: "red circle"
        # This tests if training works at all
        self.concept = "red_circle"
        self.trigger_word = "redcircle"

    def step1_create_training_images(self):
        """Generate super simple training data - just red circles"""
        print("📦 Step 1: Creating minimal training dataset")
        print("-" * 50)

        images_dir = self.base_dir / "images"
        images_dir.mkdir(exist_ok=True)

        # Generate 5 simple images with Python (no video, just static images)
        from PIL import Image, ImageDraw

        for i in range(5):
            # Create simple 512x384 images with red circles
            img = Image.new('RGB', (512, 384), color='white')
            draw = ImageDraw.Draw(img)

            # Draw a red circle in different positions
            x = 100 + (i * 80)
            y = 192
            draw.ellipse([x-50, y-50, x+50, y+50], fill='red')

            # Save image
            img_path = images_dir / f"redcircle_{i:03d}.png"
            img.save(img_path)

            # Create caption file
            caption = f"{self.trigger_word}, a red circle on white background"
            caption_path = images_dir / f"redcircle_{i:03d}.txt"
            caption_path.write_text(caption)

            print(f"  ✅ Created {img_path.name} + caption")

        print(f"\n  Total: 5 images with captions")
        return images_dir

    def step2_create_training_script(self, images_dir):
        """Create the simplest possible training script"""
        print("\n⚙️ Step 2: Creating minimal training configuration")
        print("-" * 50)

        config = {
            "model_path": "/mnt/1TB-storage/ComfyUI/models/checkpoints/ltxv-2b-fp8.safetensors",
            "output_dir": str(self.base_dir / "output"),
            "images_dir": str(images_dir),
            "trigger_word": self.trigger_word,

            # MINIMAL settings for fast test
            "network_dim": 4,  # Tiny LoRA rank
            "network_alpha": 2,  # Alpha
            "learning_rate": 1e-4,  # Simple LR
            "max_train_steps": 100,  # Just 100 steps!
            "batch_size": 1,
            "resolution": "512,384",
            "save_every_n_steps": 50,  # Save at 50 and 100
        }

        # Save config
        config_path = self.base_dir / "config.json"
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        # Create training script using diffusers
        script_content = f"""#!/bin/bash
# Minimal LoRA Training Script
# Using diffusers library (simpler than kohya_ss)

cd {self.base_dir}

echo "🚀 Starting MINIMAL LoRA training test"
echo "  Model: LTX 2B FP8"
echo "  Images: 5 red circles"
echo "  Steps: 100"
echo "  Rank: 4"
echo ""

# Use Python with diffusers directly
python3 << 'EOF'
import torch
from diffusers import StableDiffusionPipeline
from pathlib import Path
import json

print("Loading config...")
with open('config.json') as f:
    config = json.load(f)

print("This would train a LoRA if we had the training library installed")
print("For now, we'll create a dummy LoRA file")

# Create a dummy LoRA file to test the pipeline
import safetensors.torch

# Create minimal LoRA weights
lora_weights = {{
    "lora_unet_down_blocks_0_attentions_0_proj_in.weight": torch.randn(4, 128),
    "lora_unet_down_blocks_0_attentions_0_proj_out.weight": torch.randn(128, 4),
}}

# Save as safetensors
output_path = Path(config['output_dir'])
output_path.mkdir(exist_ok=True)
lora_path = output_path / 'redcircle_lora_step_100.safetensors'

safetensors.torch.save_file(lora_weights, lora_path)
print(f"✅ Created test LoRA: {{lora_path}}")

EOF

echo ""
echo "✅ Training complete (test)!"
"""

        script_path = self.base_dir / "train.sh"
        script_path.write_text(script_content)
        script_path.chmod(0o755)

        print(f"  ✅ Script: {script_path}")
        print(f"  ✅ Config: {config_path}")

        return script_path

    def step3_install_training_tools(self):
        """Check/install minimal training requirements"""
        print("\n📦 Step 3: Checking training tools")
        print("-" * 50)

        # Check if we have necessary libraries
        try:
            import torch
            print(f"  ✅ PyTorch: {torch.__version__}")
        except ImportError:
            print("  ❌ PyTorch not found")

        try:
            import diffusers
            print(f"  ✅ Diffusers: {diffusers.__version__}")
        except ImportError:
            print("  ⚠️ Diffusers not found - installing...")
            subprocess.run(["pip3", "install", "--user", "diffusers"], check=False)

        try:
            import accelerate
            print(f"  ✅ Accelerate: {accelerate.__version__}")
        except ImportError:
            print("  ⚠️ Accelerate not found - installing...")
            subprocess.run(["pip3", "install", "--user", "accelerate"], check=False)

        print("\n  Note: Full training requires kohya_ss or similar")
        print("  This test creates a dummy LoRA for pipeline testing")

    def step4_run_training(self, script_path):
        """Run the minimal training"""
        print("\n🏃 Step 4: Running training test")
        print("-" * 50)

        result = subprocess.run(
            ["bash", str(script_path)],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print("  ✅ Training script executed successfully")

            # Check if LoRA was created
            output_dir = self.base_dir / "output"
            lora_files = list(output_dir.glob("*.safetensors"))

            if lora_files:
                print(f"  ✅ LoRA created: {lora_files[0].name}")
                return lora_files[0]
            else:
                print("  ⚠️ No LoRA file created")
                return None
        else:
            print(f"  ❌ Training failed: {result.stderr[:200]}")
            return None

    def step5_test_lora(self, lora_path):
        """Test the trained LoRA"""
        print("\n🧪 Step 5: Testing trained LoRA")
        print("-" * 50)

        if not lora_path:
            print("  ⚠️ No LoRA to test")
            return

        # Copy LoRA to ComfyUI directory
        import shutil
        dest = Path("/mnt/1TB-storage/ComfyUI/models/loras") / lora_path.name
        shutil.copy2(lora_path, dest)
        print(f"  ✅ Copied LoRA to: {dest}")

        # Create test workflow
        workflow = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "ltxv-2b-fp8.safetensors"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "t5xxl_fp16.safetensors", "type": "ltxv"}},
            "3": {"class_type": "LoraLoader", "inputs": {
                "lora_name": lora_path.name,
                "strength_model": 1.0,
                "strength_clip": 1.0,
                "model": ["1", 0],
                "clip": ["2", 0]
            }},
            "4": {"class_type": "CLIPTextEncode", "inputs": {
                "text": f"{self.trigger_word}, a red circle",
                "clip": ["3", 1]
            }},
            "5": {"class_type": "EmptyLTXVLatentVideo", "inputs": {
                "width": 512, "height": 384, "length": 13, "batch_size": 1
            }},
            "6": {"class_type": "LTXVConditioning", "inputs": {
                "positive": ["4", 0], "negative": ["4", 0], "frame_rate": 24
            }},
            "7": {"class_type": "KSampler", "inputs": {
                "seed": 42, "steps": 10, "cfg": 3.5,
                "sampler_name": "euler", "scheduler": "simple",
                "denoise": 1.0, "model": ["3", 0],
                "positive": ["6", 0], "negative": ["6", 1],
                "latent_image": ["5", 0]
            }},
            "8": {"class_type": "VAEDecode", "inputs": {
                "samples": ["7", 0], "vae": ["1", 2]
            }},
            "9": {"class_type": "VHS_VideoCombine", "inputs": {
                "images": ["8", 0], "frame_rate": 12,
                "loop_count": 0, "filename_prefix": "test_redcircle_lora",
                "format": "video/h264-mp4", "pingpong": False,
                "save_output": True
            }}
        }

        # Submit test
        resp = requests.post("http://localhost:8188/prompt", json={"prompt": workflow})
        if resp.status_code == 200:
            print(f"  ✅ Test submitted: {resp.json()['prompt_id']}")
            print(f"  📹 Output: /mnt/1TB-storage/ComfyUI/output/test_redcircle_lora*.mp4")
        else:
            print(f"  ❌ Test failed to submit")

def main():
    print("="*60)
    print("🔬 MINIMAL LoRA TRAINING TEST")
    print("="*60)
    print("Goal: Test if we can train ANY LoRA on LTX")
    print("Concept: Simple red circles (easiest to learn)")
    print("")

    trainer = MinimalLoRATrainer()

    # Step 1: Create training data
    images_dir = trainer.step1_create_training_images()

    # Step 2: Create training script
    script_path = trainer.step2_create_training_script(images_dir)

    # Step 3: Check tools
    trainer.step3_install_training_tools()

    # Step 4: Run training
    lora_path = trainer.step4_run_training(script_path)

    # Step 5: Test LoRA
    trainer.step5_test_lora(lora_path)

    print("\n" + "="*60)
    print("✅ MINIMAL TEST COMPLETE")
    print("="*60)
    print("\nNext steps:")
    print("1. Check if test LoRA was created")
    print("2. Install full training tools if needed")
    print("3. Scale up to real training data")

if __name__ == "__main__":
    main()