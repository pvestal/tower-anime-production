#!/usr/bin/env python3
"""Debug script to test basic AnimateDiff video generation"""
import json
import requests
import time
import os

def test_basic_animatediff_workflow():
    """Test simplest possible AnimateDiff workflow"""

    workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": "realisticVision_v51.safetensors"
            }
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "beautiful woman, Zara, sitting in a cafe, working on laptop, masterpiece, best quality",
                "clip": ["1", 1]
            }
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "worst quality, low quality, deformed, bad anatomy",
                "clip": ["1", 1]
            }
        },
        "4": {
            "class_type": "ADE_AnimateDiffLoaderWithContext",
            "inputs": {
                "model": ["1", 0],
                "model_name": "mm_sd_v15_v2.ckpt",
                "beta_schedule": "sqrt_linear (AnimateDiff)",
                "motion_scale": 1.0,
                "apply_v2_models_properly": False,
                "ad_keyframes": None
            }
        },
        "5": {
            "class_type": "ADE_EmptyLatentImageLarge",
            "inputs": {
                "width": 512,
                "height": 768,
                "batch_size": 16  # 16 frames for 2 second test
            }
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["4", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["5", 0],
                "seed": 12345,
                "steps": 20,
                "cfg": 7.5,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0
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
            "class_type": "CreateVideo",
            "inputs": {
                "images": ["7", 0],
                "fps": 8.0
            }
        },
        "9": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["8", 0],
                "filename_prefix": "debug_zara_video_test",
                "format": "mp4",
                "codec": "h264"
            }
        },
        "10": {
            "class_type": "SaveAnimatedWEBP",
            "inputs": {
                "images": ["7", 0],
                "fps": 8,
                "lossless": False,
                "quality": 80,
                "method": "default",
                "filename_prefix": "debug_zara_webp_test"
            }
        }
    }

    print("=" * 60)
    print("ANIMATEDIFF VIDEO GENERATION DEBUG TEST")
    print("=" * 60)
    print("\n1. Submitting basic AnimateDiff test workflow...")

    try:
        response = requests.post(
            "http://localhost:8188/prompt",
            json={"prompt": workflow}
        )

        if response.status_code == 200:
            prompt_id = response.json()["prompt_id"]
            print(f"✓ Workflow submitted successfully")
            print(f"  Prompt ID: {prompt_id}")
            print("\n2. Monitoring generation progress...")

            # Monitor progress
            start_time = time.time()
            last_status = ""

            for i in range(120):  # Wait up to 120 seconds
                time.sleep(2)

                # Check queue status
                queue_resp = requests.get("http://localhost:8188/queue")
                if queue_resp.status_code == 200:
                    queue = queue_resp.json()
                    running = queue.get("queue_running", [])
                    pending = queue.get("queue_pending", [])

                    status = f"  [{i*2:3d}s] Running: {len(running)}, Pending: {len(pending)}"
                    if status != last_status:
                        print(status)
                        last_status = status

                # Check history for completion
                history = requests.get("http://localhost:8188/history").json()

                if prompt_id in history:
                    elapsed = time.time() - start_time
                    print(f"\n✓ Workflow completed in {elapsed:.1f} seconds!")

                    # Check outputs
                    outputs = history[prompt_id].get("outputs", {})
                    print(f"\n3. Checking outputs...")
                    print(f"  Output nodes: {list(outputs.keys())}")

                    # Look for video output
                    video_found = False
                    for node_id, node_output in outputs.items():
                        if "gifs" in node_output or "videos" in node_output:
                            print(f"  ✓ Video output found in node {node_id}")
                            if "gifs" in node_output:
                                for gif in node_output["gifs"]:
                                    filename = gif.get("filename", "")
                                    print(f"    - GIF: {filename}")
                            if "videos" in node_output:
                                for video in node_output["videos"]:
                                    filename = video.get("filename", "")
                                    print(f"    - Video: {filename}")
                                    video_found = True

                    # Check output directory
                    print(f"\n4. Checking output directory...")
                    output_dir = "/mnt/1TB-storage/ComfyUI/output"
                    recent_files = []

                    for file in os.listdir(output_dir):
                        if "debug_zara_video_test" in file:
                            filepath = os.path.join(output_dir, file)
                            size = os.path.getsize(filepath) / 1024 / 1024  # MB
                            recent_files.append((file, size))

                    if recent_files:
                        print(f"  ✓ Found {len(recent_files)} output files:")
                        for filename, size in recent_files:
                            print(f"    - {filename} ({size:.2f} MB)")
                        video_found = True
                    else:
                        print(f"  ✗ No output files found with prefix 'debug_zara_video_test'")

                    print("\n" + "=" * 60)
                    if video_found:
                        print("TEST RESULT: ✓ PASSED - Video generation working!")
                    else:
                        print("TEST RESULT: ✗ FAILED - No video output created")
                        print("\nTroubleshooting:")
                        print("1. Check ComfyUI console for errors")
                        print("2. Verify VHS_VideoCombine node is installed")
                        print("3. Check ffmpeg is available: which ffmpeg")
                    print("=" * 60)

                    return video_found

            print(f"\n✗ Workflow timed out after 120 seconds")
            print("  Check ComfyUI console for errors")
            return False

        else:
            print(f"✗ Failed to submit workflow")
            print(f"  Status: {response.status_code}")
            print(f"  Error: {response.text}")
            return False

    except Exception as e:
        print(f"✗ Exception occurred: {str(e)}")
        return False

if __name__ == "__main__":
    print("Starting AnimateDiff video generation test...")
    print("This will generate a 2-second test video of Zara.\n")

    success = test_basic_animatediff_workflow()

    if not success:
        print("\nDebug suggestions:")
        print("1. Check if ComfyUI is running: curl http://localhost:8188/")
        print("2. Check available nodes: curl http://localhost:8188/object_info | grep VHS")
        print("3. Check motion models: ls /mnt/1TB-storage/ComfyUI/models/animatediff_models/")
        print("4. Monitor ComfyUI logs: tail -f /mnt/1TB-storage/ComfyUI/log.txt")

    exit(0 if success else 1)