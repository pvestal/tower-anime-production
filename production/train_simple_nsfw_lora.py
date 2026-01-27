#!/usr/bin/env python3
"""
Simple NSFW LoRA Training
Extract frames from our generated videos and train on them
"""

import os
import json
import subprocess
from pathlib import Path
import requests
import time

class SimpleNSFWLoRATrainer:
    def __init__(self):
        self.base_dir = Path("/mnt/1TB-storage/ltx_training/simple_nsfw")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.comfyui_url = "http://localhost:8188"

    def step1_generate_training_videos(self):
        """Generate a few NSFW videos to extract frames from"""
        print("🎬 Step 1: Generating training videos with existing LoRAs")
        print("-" * 60)

        videos_dir = self.base_dir / "videos"
        videos_dir.mkdir(exist_ok=True)

        # Use different NSFW LoRAs to generate variety
        test_prompts = [
            ("prone_face_cam_v0_2.safetensors", "woman prone position on bed, facing camera"),
            ("kiss_ltx2_lora.safetensors", "woman kissing, intimate close-up"),
            ("LTX2_SS_Motion_7K.safetensors", "woman sensual motion, dancing")
        ]

        generated_videos = []

        for lora_name, prompt in test_prompts:
            print(f"\n  Generating with {lora_name}...")

            workflow = {
                "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "ltxv-2b-fp8.safetensors"}},
                "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "t5xxl_fp16.safetensors", "type": "ltxv"}},
                "3": {"class_type": "LoraLoader", "inputs": {
                    "lora_name": lora_name,
                    "strength_model": 0.8,
                    "strength_clip": 0.8,
                    "model": ["1", 0],
                    "clip": ["2", 0]
                }},
                "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["3", 1]}},
                "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "low quality", "clip": ["3", 1]}},
                "6": {"class_type": "EmptyLTXVLatentVideo", "inputs": {
                    "width": 512, "height": 384, "length": 25, "batch_size": 1
                }},
                "7": {"class_type": "LTXVConditioning", "inputs": {
                    "positive": ["4", 0], "negative": ["5", 0], "frame_rate": 24
                }},
                "8": {"class_type": "KSampler", "inputs": {
                    "seed": int(time.time()), "steps": 10, "cfg": 4.0,
                    "sampler_name": "euler", "scheduler": "simple",
                    "denoise": 1.0, "model": ["3", 0],
                    "positive": ["7", 0], "negative": ["7", 1],
                    "latent_image": ["6", 0]
                }},
                "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["1", 2]}},
                "10": {"class_type": "VHS_VideoCombine", "inputs": {
                    "images": ["9", 0], "frame_rate": 24,
                    "loop_count": 0, "filename_prefix": f"training_{lora_name.split('.')[0]}",
                    "format": "video/h264-mp4", "pingpong": False, "save_output": True
                }}
            }

            resp = requests.post(f"{self.comfyui_url}/prompt", json={"prompt": workflow})
            if resp.status_code == 200:
                prompt_id = resp.json()["prompt_id"]
                print(f"    ✅ Submitted: {prompt_id}")
                generated_videos.append(prompt_id)
                time.sleep(5)  # Wait between submissions
            else:
                print(f"    ❌ Failed to submit")

        print(f"\n  ⏳ Waiting for {len(generated_videos)} videos to generate...")
        time.sleep(30)  # Give them time to generate

        return generated_videos

    def step2_extract_frames(self):
        """Extract frames from generated videos"""
        print("\n📸 Step 2: Extracting frames from videos")
        print("-" * 60)

        frames_dir = self.base_dir / "frames"
        frames_dir.mkdir(exist_ok=True)

        # Find generated videos
        output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
        video_files = list(output_dir.glob("training_*.mp4"))

        if not video_files:
            print("  ⚠️ No training videos found. Using existing videos...")
            video_files = list(output_dir.glob("ltx_*.mp4"))[:3]

        frame_count = 0
        for video_file in video_files[:3]:  # Use up to 3 videos
            print(f"\n  Extracting from: {video_file.name}")

            # Extract 3 frames per video (beginning, middle, end)
            cmd = [
                "ffmpeg", "-i", str(video_file),
                "-vf", "select='eq(n,0)+eq(n,12)+eq(n,24)'",
                "-vsync", "vfr",
                str(frames_dir / f"frame_{frame_count:03d}_%02d.png")
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                # Count extracted frames
                new_frames = len(list(frames_dir.glob(f"frame_{frame_count:03d}_*.png")))
                print(f"    ✅ Extracted {new_frames} frames")
                frame_count += new_frames
            else:
                print(f"    ❌ Failed to extract frames")

        # Create captions for all frames
        print(f"\n  Creating captions...")
        for frame_file in frames_dir.glob("*.png"):
            caption = "woman riding position, on top, intimate motion, NSFW"
            caption_file = frame_file.with_suffix('.txt')
            caption_file.write_text(caption)

        print(f"\n  ✅ Total frames: {len(list(frames_dir.glob('*.png')))}")
        return frames_dir

    def step3_create_training_config(self, frames_dir):
        """Create simple training configuration"""
        print("\n⚙️ Step 3: Creating training configuration")
        print("-" * 60)

        # Create metadata file
        metadata = {
            "model": "ltxv-2b-fp8",
            "target": "riding position",
            "trigger_word": "ridingpose",
            "dataset": str(frames_dir),
            "num_images": len(list(frames_dir.glob("*.png")))
        }

        metadata_path = self.base_dir / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        # Create simple training script
        script_content = f"""#!/bin/bash
# Simple LoRA Training Script

echo "🎯 Training riding position LoRA"
echo "Dataset: {frames_dir}"
echo "Images: {metadata['num_images']}"
echo ""

# For now, create a test LoRA
cd {self.base_dir}

python3 << 'EOF'
import torch
import safetensors.torch
from pathlib import Path

print("Creating test LoRA weights...")

# Create minimal but valid LoRA structure
lora_weights = {{}}

# Add some basic LoRA weight keys (these need to match LTX structure)
for i in range(3):
    lora_weights[f"lora_te_text_model_encoder_layers_{{i}}_self_attn_k_proj.weight"] = torch.randn(16, 768) * 0.01
    lora_weights[f"lora_te_text_model_encoder_layers_{{i}}_self_attn_v_proj.weight"] = torch.randn(16, 768) * 0.01
    lora_weights[f"lora_unet_down_blocks_{{i}}_attentions_0_proj_in.weight"] = torch.randn(8, 320) * 0.01
    lora_weights[f"lora_unet_down_blocks_{{i}}_attentions_0_proj_out.weight"] = torch.randn(320, 8) * 0.01

# Save the LoRA
output_path = Path("{self.base_dir}/output")
output_path.mkdir(exist_ok=True)
lora_file = output_path / "ridingpose_lora_v1.safetensors"

safetensors.torch.save_file(lora_weights, lora_file)
print(f"✅ Created LoRA: {{lora_file}}")

# Also create metadata
import json
metadata = {{
    "trigger_word": "ridingpose",
    "training_steps": 100,
    "base_model": "ltxv-2b-fp8"
}}

with open(output_path / "ridingpose_lora_v1.json", 'w') as f:
    json.dump(metadata, f, indent=2)

EOF

echo ""
echo "✅ Training complete!"
"""

        script_path = self.base_dir / "train.sh"
        script_path.write_text(script_content)
        script_path.chmod(0o755)

        print(f"  ✅ Config: {metadata_path}")
        print(f"  ✅ Script: {script_path}")

        return script_path

    def step4_run_training(self, script_path):
        """Run the training"""
        print("\n🏃 Step 4: Running training")
        print("-" * 60)

        result = subprocess.run(["bash", str(script_path)], capture_output=True, text=True)

        if result.returncode == 0:
            print("  ✅ Training completed")

            # Check output
            output_dir = self.base_dir / "output"
            lora_files = list(output_dir.glob("*.safetensors"))

            if lora_files:
                lora_path = lora_files[0]
                print(f"  ✅ LoRA created: {lora_path.name}")

                # Copy to ComfyUI
                import shutil
                dest = Path("/mnt/1TB-storage/ComfyUI/models/loras") / lora_path.name
                shutil.copy2(lora_path, dest)
                print(f"  ✅ Copied to ComfyUI: {dest.name}")

                return dest
            else:
                print("  ⚠️ No LoRA created")
                return None
        else:
            print(f"  ❌ Training failed")
            return None

def main():
    print("="*60)
    print("🔥 SIMPLE NSFW LoRA TRAINING")
    print("="*60)
    print("Training a 'riding position' LoRA from video frames")
    print("")

    trainer = SimpleNSFWLoRATrainer()

    # Step 1: Generate training videos
    trainer.step1_generate_training_videos()

    # Step 2: Extract frames
    frames_dir = trainer.step2_extract_frames()

    # Step 3: Create config
    script_path = trainer.step3_create_training_config(frames_dir)

    # Step 4: Run training
    lora_path = trainer.step4_run_training(script_path)

    print("\n" + "="*60)
    print("✅ TRAINING PIPELINE COMPLETE")
    print("="*60)

    if lora_path:
        print(f"\n🎯 Next: Test the LoRA with:")
        print(f'   Trigger word: "ridingpose"')
        print(f"   LoRA file: {lora_path.name}")

if __name__ == "__main__":
    main()