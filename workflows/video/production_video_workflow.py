#!/usr/bin/env python3
"""
Production Video Workflow with Character Consistency
Implements deterministic seed strategy, IP-Adapter, and chunked generation
"""
import json
import requests
import uuid
import time
import os
from datetime import datetime

COMFYUI_URL = "http://localhost:8188"

class ProductionVideoGenerator:
    def __init__(self):
        self.base_seed = 888888
        self.character_prompt = "beautiful anime girl with silver long hair, violet eyes, purple dress"
        self.negative_prompt = "blurry, deformed, extra limbs, inconsistent face, morphing features"
        self.cfg_scale = 8.5
        self.resolution = (512, 768)
        self.frames_per_chunk = 24  # 2 seconds at 12fps
        self.fps = 12
        self.reference_image = None

    def generate_reference_sheet(self):
        """Generate character reference sheet with multiple angles"""

        angles = ["front view", "profile left", "profile right", "three-quarter view", "back view"]
        workflow = {
            "checkpoint": {
                "inputs": {
                    "ckpt_name": "dreamshaper_8.safetensors"
                },
                "class_type": "CheckpointLoaderSimple"
            }
        }

        reference_images = []

        for idx, angle in enumerate(angles):
            node_prefix = f"angle_{idx}"

            # Consistent prompt with angle variation
            workflow[f"{node_prefix}_prompt"] = {
                "inputs": {
                    "text": f"{self.character_prompt}, {angle}, consistent character, same person, identical face, model sheet",
                    "clip": ["checkpoint", 1]
                },
                "class_type": "CLIPTextEncode"
            }

            workflow[f"{node_prefix}_negative"] = {
                "inputs": {
                    "text": self.negative_prompt,
                    "clip": ["checkpoint", 1]
                },
                "class_type": "CLIPTextEncode"
            }

            workflow[f"{node_prefix}_latent"] = {
                "inputs": {
                    "width": self.resolution[0],
                    "height": self.resolution[1],
                    "batch_size": 1
                },
                "class_type": "EmptyLatentImage"
            }

            # Use base seed for all angles
            workflow[f"{node_prefix}_sample"] = {
                "inputs": {
                    "seed": self.base_seed,
                    "steps": 25,
                    "cfg": self.cfg_scale,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["checkpoint", 0],
                    "positive": [f"{node_prefix}_prompt", 0],
                    "negative": [f"{node_prefix}_negative", 0],
                    "latent_image": [f"{node_prefix}_latent", 0]
                },
                "class_type": "KSampler"
            }

            workflow[f"{node_prefix}_decode"] = {
                "inputs": {
                    "samples": [f"{node_prefix}_sample", 0],
                    "vae": ["checkpoint", 2]
                },
                "class_type": "VAEDecode"
            }

            workflow[f"{node_prefix}_save"] = {
                "inputs": {
                    "filename_prefix": f"reference_sheet_{angle.replace(' ', '_')}",
                    "images": [f"{node_prefix}_decode", 0]
                },
                "class_type": "SaveImage"
            }

            reference_images.append([f"{node_prefix}_decode", 0])

        return {"prompt": workflow}

    def generate_video_chunk_with_ipadapter(self, chunk_num, scene_description, reference_image_path=None):
        """Generate video chunk with IP-Adapter for character consistency"""

        # Deterministic seed offset strategy
        chunk_seed = self.base_seed + chunk_num

        workflow = {
            "checkpoint": {
                "inputs": {
                    "ckpt_name": "dreamshaper_8.safetensors"
                },
                "class_type": "CheckpointLoaderSimple"
            },

            "clip_vision": {
                "inputs": {
                    "clip_name": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"
                },
                "class_type": "CLIPVisionLoader"
            },

            "ipadapter_model": {
                "inputs": {
                    "ipadapter_file": "ip-adapter-faceid-plusv2_sd15.bin"
                },
                "class_type": "IPAdapterModelLoader"
            }
        }

        # Load reference image if provided
        if reference_image_path and os.path.exists(reference_image_path):
            workflow["reference_image"] = {
                "inputs": {
                    "image": reference_image_path,
                    "upload": "image"
                },
                "class_type": "LoadImage"
            }

            # Apply IP-Adapter
            workflow["ipadapter_apply"] = {
                "inputs": {
                    "weight": 0.7,  # Moderate weight for balance
                    "weight_type": "linear",
                    "combine_embeds": "concat",
                    "start_at": 0,
                    "end_at": 1,
                    "embeds_scaling": "V only",
                    "model": ["checkpoint", 0],
                    "ipadapter": ["ipadapter_model", 0],
                    "image": ["reference_image", 0],
                    "clip_vision": ["clip_vision", 0]
                },
                "class_type": "IPAdapterAdvanced"
            }

            model_connection = ["ipadapter_apply", 0]
        else:
            model_connection = ["checkpoint", 0]

        # Scene prompt with consistency keywords
        workflow["positive"] = {
            "inputs": {
                "text": f"{self.character_prompt}, {scene_description}, consistent character, same person, identical face",
                "clip": ["checkpoint", 1]
            },
            "class_type": "CLIPTextEncode"
        }

        workflow["negative"] = {
            "inputs": {
                "text": self.negative_prompt,
                "clip": ["checkpoint", 1]
            },
            "class_type": "CLIPTextEncode"
        }

        # Generate batch of frames
        workflow["latent"] = {
            "inputs": {
                "width": self.resolution[0],
                "height": self.resolution[1],
                "batch_size": self.frames_per_chunk
            },
            "class_type": "EmptyLatentImage"
        }

        # Sample with deterministic seed
        workflow["sample"] = {
            "inputs": {
                "seed": chunk_seed,
                "steps": 20,
                "cfg": self.cfg_scale,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": model_connection,
                "positive": ["positive", 0],
                "negative": ["negative", 0],
                "latent_image": ["latent", 0]
            },
            "class_type": "KSampler"
        }

        workflow["decode"] = {
            "inputs": {
                "samples": ["sample", 0],
                "vae": ["checkpoint", 2]
            },
            "class_type": "VAEDecode"
        }

        # Save as animated chunk
        workflow["save"] = {
            "inputs": {
                "filename_prefix": f"production_chunk_{chunk_num:03d}",
                "fps": self.fps,
                "lossless": False,
                "quality": 92,
                "method": "default",
                "images": ["decode", 0]
            },
            "class_type": "SaveAnimatedWEBP"
        }

        return {"prompt": workflow}

    def submit_workflow(self, workflow, description=""):
        """Submit workflow and monitor completion"""

        client_id = str(uuid.uuid4())
        workflow["client_id"] = client_id

        print(f"  {description}: Submitting...", end="")

        response = requests.post(f"{COMFYUI_URL}/prompt", json=workflow)

        if response.status_code != 200:
            print(f" ❌ Failed")
            return None

        result = response.json()
        prompt_id = result.get("prompt_id", client_id)

        # Monitor completion
        start_time = time.time()
        dots = 0

        while time.time() - start_time < 120:
            if dots < 15:
                print(".", end="", flush=True)
                dots += 1

            response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
            if response.status_code == 200:
                history = response.json()
                if prompt_id in history:
                    job = history[prompt_id]
                    if job.get("status", {}).get("completed"):
                        print(" ✅")
                        outputs = job.get("outputs", {})
                        for node_id, output in outputs.items():
                            if "images" in output:
                                for img in output["images"]:
                                    if "filename" in img:
                                        return img["filename"]
                        return True

            time.sleep(2)

        print(" ⏰ Timeout")
        return None

    def generate_full_video(self, scene_descriptions):
        """Generate full video with multiple chunks"""

        print("=" * 70)
        print("🎬 PRODUCTION VIDEO GENERATION WITH CHARACTER CONSISTENCY")
        print("=" * 70)

        # Step 1: Generate reference sheet
        print("\n📸 Step 1: Generating character reference sheet...")
        ref_workflow = self.generate_reference_sheet()
        ref_result = self.submit_workflow(ref_workflow, "Reference sheet")

        # Use first reference image for IP-Adapter (in production, you'd pick the best one)
        reference_path = "/mnt/1TB-storage/ComfyUI/output/reference_sheet_front_view_00001_.png"

        # Step 2: Generate video chunks
        print("\n🎬 Step 2: Generating video chunks with IP-Adapter...")
        chunk_files = []

        for chunk_num, scene_desc in enumerate(scene_descriptions):
            workflow = self.generate_video_chunk_with_ipadapter(
                chunk_num,
                scene_desc,
                reference_path if chunk_num > 0 else None  # Use reference after first chunk
            )
            result = self.submit_workflow(workflow, f"Chunk {chunk_num}")
            if result:
                chunk_files.append(result)

        # Summary
        print("\n" + "=" * 70)
        print("📊 PRODUCTION RESULTS")
        print("=" * 70)
        print(f"\n✅ Reference sheet generated")
        print(f"✅ Video chunks generated: {len(chunk_files)}")

        print("\n🔑 Production Settings Used:")
        print(f"  • Base seed: {self.base_seed}")
        print(f"  • Seed strategy: Base + chunk_num offset")
        print(f"  • CFG scale: {self.cfg_scale}")
        print(f"  • Frames per chunk: {self.frames_per_chunk}")
        print(f"  • IP-Adapter weight: 0.7")

        print("\n💡 Next Steps:")
        print("1. Review reference sheet for best angle")
        print("2. Use ffmpeg to combine chunks if needed")
        print("3. Consider adding ControlNet for specific poses")
        print("4. Test with AnimateDiff for smoother motion")

        return chunk_files


def main():
    generator = ProductionVideoGenerator()

    # Define your video scenes
    scenes = [
        "walking in garden, morning sunlight, birds flying",
        "sitting on bench, reading book, peaceful expression",
        "standing up, stretching arms, looking at sky",
        "walking towards camera, smiling warmly",
        "waving goodbye, sunset lighting, golden hour"
    ]

    # Generate the full video
    results = generator.generate_full_video(scenes)

    print(f"\n📁 Files saved to: /mnt/1TB-storage/ComfyUI/output/")
    print("=" * 70)


if __name__ == "__main__":
    main()