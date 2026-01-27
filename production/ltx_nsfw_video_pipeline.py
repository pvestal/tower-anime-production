#!/usr/bin/env python3
"""
LTX NSFW Video Pipeline for Tokyo Debt Desire
Integrates newly uploaded LTXV NSFW LoRAs with character generation
"""

import asyncio
import logging
from pathlib import Path
import json
import time
import aiohttp
import psycopg2
from tokyo_debt_desire_pipeline import TokyoDebtDesirePipeline

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LTXNSFWVideoPipeline(TokyoDebtDesirePipeline):
    """NSFW Video generation using LTX 2B with adult LoRAs"""

    def __init__(self):
        super().__init__()

        # Available NSFW LTXV LoRAs (uploaded Jan 26)
        self.nsfw_ltx_loras = {
            'orgasm': 'LTX-2_-_Orgasm_v1.safetensors',  # 805MB
            'better_female': 'LTX-2_-_Better_Female_Nudity.safetensors',  # 805MB
            'sexgod': 'SexGod_Nudity_LTX2_v1_5.safetensors',  # 805MB
            'furry': 'ltx2_nsfwfurry_lora_step_15000.safetensors',  # 1.2GB
            'kiss': 'kiss_ltx2_lora.safetensors',  # 855MB
            'prone': 'prone_face_cam_v0_2.safetensors',  # 855MB
            'motion': 'LTX2_SS_Motion_7K.safetensors',  # 402MB
            'dream': 'DreamLTXV.safetensors',  # 190MB
            'dr34ml4y': 'DR34ML4Y_I2V_14B_LOW_V2.safetensors'  # 306MB
        }

        # LTX model paths (2B models that actually fit in 12GB VRAM)
        self.ltx_model = "ltxv-2b-fp8.safetensors"  # 4GB model
        self.ltx_vae = "ltx_vae.safetensors"

    async def generate_nsfw_ltx_video(
        self,
        character_name: str = "Mei Kobayashi",
        nsfw_type: str = "better_female",
        prompt_addon: str = "intimate scene",
        duration: float = 5.0
    ):
        """Generate NSFW video with LTX and character LoRA"""

        logger.info(f"🔞 Generating NSFW LTX Video")
        logger.info(f"   Character: {character_name}")
        logger.info(f"   NSFW LoRA: {self.nsfw_ltx_loras.get(nsfw_type, 'default')}")
        logger.info(f"   Duration: {duration} seconds")

        # Get character LoRA
        character_lora = None
        if character_name == "Mei Kobayashi":
            character_lora = self.mei_loras.get('body', 'mei_body.safetensors')

        # Get NSFW LoRA
        nsfw_lora = self.nsfw_ltx_loras.get(nsfw_type, self.nsfw_ltx_loras['better_female'])

        # Build prompt
        if character_name == "Mei Kobayashi":
            base_prompt = "mei, beautiful japanese woman"
        else:
            base_prompt = f"{character_name}"

        full_prompt = f"{base_prompt}, {prompt_addon}, high quality, detailed"
        negative_prompt = "low quality, blurry, distorted"

        timestamp = int(time.time())
        filename = f"ltx_nsfw_{character_name.replace(' ', '_')}_{nsfw_type}_{timestamp}"

        # Create LTX video workflow
        workflow = self._create_ltx_nsfw_workflow(
            prompt=full_prompt,
            negative=negative_prompt,
            character_lora=character_lora,
            nsfw_lora=nsfw_lora,
            duration=duration,
            filename=filename
        )

        # Submit to ComfyUI
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.comfyui_url}/prompt",
                json={"prompt": workflow}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    prompt_id = result.get("prompt_id")

                    if prompt_id:
                        # Wait for video generation (longer for video)
                        video_path = await self._wait_for_video(filename, timeout=300)

                        if video_path:
                            logger.info(f"✅ Generated NSFW video: {video_path}")

                            # Log to database
                            conn = self.get_db_connection()
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO generated_assets (file_path, file_type, metadata)
                                VALUES (%s, %s, %s)
                            """, (
                                video_path,
                                'video',
                                json.dumps({
                                    'character': character_name,
                                    'project': 'Tokyo Debt Desire',
                                    'content_rating': 'explicit',
                                    'nsfw_lora': nsfw_type,
                                    'duration': duration,
                                    'model': 'LTX-2B',
                                    'timestamp': timestamp
                                })
                            ))
                            conn.commit()
                            conn.close()

                            return video_path
                        else:
                            logger.error("❌ Video generation timeout")
                else:
                    error = await response.text()
                    logger.error(f"❌ ComfyUI error: {error}")

        return None

    def _create_ltx_nsfw_workflow(
        self,
        prompt: str,
        negative: str,
        character_lora: str,
        nsfw_lora: str,
        duration: float,
        filename: str
    ):
        """Create LTX video workflow with NSFW LoRAs"""

        workflow = {
            # Load LTX model
            "1": {
                "class_type": "LTXVModelLoader",
                "inputs": {
                    "model": self.ltx_model
                }
            },
            # Load VAE
            "2": {
                "class_type": "VAELoader",
                "inputs": {
                    "vae_name": self.ltx_vae
                }
            },
            # Text encoders
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["1", 1]
                }
            },
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": negative,
                    "clip": ["1", 1]
                }
            }
        }

        # Add character LoRA if available
        model_output = ["1", 0]
        clip_output = ["1", 1]

        if character_lora:
            workflow["5"] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": character_lora,
                    "strength_model": 0.8,
                    "strength_clip": 0.8,
                    "model": model_output,
                    "clip": clip_output
                }
            }
            model_output = ["5", 0]
            clip_output = ["5", 1]

        # Add NSFW LoRA
        workflow["6"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": nsfw_lora,
                "strength_model": 1.0,
                "strength_clip": 1.0,
                "model": model_output,
                "clip": clip_output
            }
        }

        # LTX Video Sampler
        workflow["7"] = {
            "class_type": "LTXVSampler",
            "inputs": {
                "model": ["6", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "steps": 20,
                "cfg": 3.5,
                "seed": int(time.time()),
                "fps": 24,
                "duration": duration,
                "width": 768,
                "height": 512
            }
        }

        # VAE Decode
        workflow["8"] = {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["7", 0],
                "vae": ["2", 0]
            }
        }

        # Save video
        workflow["9"] = {
            "class_type": "VHSVideoCombine",
            "inputs": {
                "images": ["8", 0],
                "fps": 24,
                "format": "mp4",
                "filename_prefix": filename
            }
        }

        return workflow

    async def _wait_for_video(self, filename_prefix: str, timeout: int = 300):
        """Wait for video file to be generated"""

        output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Check for video files
            for ext in ['.mp4', '.webm', '.mov']:
                pattern = f"{filename_prefix}*{ext}"
                files = list(output_dir.glob(pattern))

                if files:
                    return str(files[0])

            await asyncio.sleep(2)

        return None

async def main():
    """Test NSFW LTX video generation"""

    logger.info("🔞 LTX NSFW Video Pipeline Test")
    logger.info("=" * 60)
    logger.info("Available NSFW LoRAs:")

    pipeline = LTXNSFWVideoPipeline()

    for key, lora in pipeline.nsfw_ltx_loras.items():
        logger.info(f"   - {key}: {lora}")

    logger.info("")

    # Test different NSFW types
    test_cases = [
        {
            "character": "Mei Kobayashi",
            "nsfw_type": "better_female",
            "prompt": "professional photoshoot, elegant pose",
            "duration": 3.0
        },
        {
            "character": "Mei Kobayashi",
            "nsfw_type": "kiss",
            "prompt": "intimate close-up, looking at camera",
            "duration": 2.0
        }
    ]

    for test in test_cases:
        logger.info(f"\n📹 Generating: {test['character']} with {test['nsfw_type']}")

        result = await pipeline.generate_nsfw_ltx_video(
            character_name=test['character'],
            nsfw_type=test['nsfw_type'],
            prompt_addon=test['prompt'],
            duration=test['duration']
        )

        if result:
            logger.info(f"✅ Success: {Path(result).name}")
        else:
            logger.info("❌ Generation failed")

    logger.info("\n" + "=" * 60)
    logger.info("✅ NSFW LTX Video pipeline ready for Tokyo Debt Desire!")

if __name__ == "__main__":
    asyncio.run(main())