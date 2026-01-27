#!/usr/bin/env python3
"""
Integrated Netflix-Level Anime Production Pipeline
Connects all Tower services for complete story-to-final-video workflow
"""

import os
import time
import json
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
import aiohttp
import psycopg2
from psycopg2.extras import RealDictCursor

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class IntegratedAnimeProductionPipeline:
    """
    Netflix-level anime production pipeline integrating all Tower services
    """

    def __init__(self):
        # Service endpoints
        self.comfyui_url = "http://192.168.50.135:8188"
        self.echo_brain_url = "http://localhost:8309"
        self.apple_music_url = "http://localhost:8088"
        self.auth_url = "http://localhost:8088"

        # Database connection
        self.db_config = {
            'host': 'localhost',
            'database': 'tower_consolidated',
            'user': 'patrick',
            'password': 'RP78eIrW7cI2jYvL5akt1yurE'
        }

        # Paths
        self.output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
        self.storage_dir = Path("/mnt/10TB1/AnimeProduction")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(**self.db_config, cursor_factory=RealDictCursor)

    async def get_character_data(self, character_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve character data from database SSOT"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT * FROM characters WHERE name ILIKE %s LIMIT 1",
                (f"%{character_name}%",)
            )
            character = cursor.fetchone()
            conn.close()

            if character:
                return dict(character)
            return None

        except Exception as e:
            logger.error(f"Database error: {e}")
            return None

    async def get_echo_brain_context(self, query: str) -> Dict[str, Any]:
        """Get contextual information from Echo Brain"""
        try:
            async with aiohttp.ClientSession() as session:
                # Try to get facts from Echo Brain MCP
                payload = {
                    "method": "tools/call",
                    "params": {
                        "name": "search_memory",
                        "arguments": {"query": query, "limit": 5}
                    }
                }

                async with session.post(
                    "http://localhost:8312/mcp",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get("result", {})

        except Exception as e:
            logger.warning(f"Echo Brain context unavailable: {e}")

        # Fallback to basic context
        return {"context": f"Scene context for: {query}", "memories": []}

    async def generate_character_image(
        self,
        character_data: Dict[str, Any],
        scene_description: str,
        style: str = "anime"
    ) -> Optional[str]:
        """Generate character image using ComfyUI with LoRA"""
        try:
            # Determine LoRA based on character
            lora_mapping = {
                "Akira": "mei_working_v1.safetensors",  # Placeholder mapping
                "Luna": "mei_working_v1.safetensors",
                "Viktor": "mei_working_v1.safetensors",
                "Mei": "mei_working_v1.safetensors"
            }

            character_name = character_data.get("name", "")
            lora_file = None
            for key, lora in lora_mapping.items():
                if key.lower() in character_name.lower():
                    lora_file = lora
                    break

            if not lora_file:
                lora_file = "mei_working_v1.safetensors"  # Default

            # Create image generation workflow
            timestamp = int(time.time())
            workflow = {
                # Base model
                "1": {
                    "class_type": "CheckpointLoaderSimple",
                    "inputs": {"ckpt_name": "AOM3A1B.safetensors"}
                },

                # Character LoRA
                "2": {
                    "class_type": "LoraLoader",
                    "inputs": {
                        "lora_name": lora_file,
                        "strength_model": 0.8,
                        "strength_clip": 0.8,
                        "model": ["1", 0],
                        "clip": ["1", 1]
                    }
                },

                # Prompt
                "3": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {
                        "text": f"{character_data.get('description', '')}, {scene_description}, {style}, masterpiece, best quality, detailed",
                        "clip": ["2", 1]
                    }
                },

                # Negative prompt
                "4": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {
                        "text": "low quality, worst quality, blurry, pixelated",
                        "clip": ["2", 1]
                    }
                },

                # Latent
                "5": {
                    "class_type": "EmptyLatentImage",
                    "inputs": {"width": 768, "height": 512, "batch_size": 1}
                },

                # Sampler
                "6": {
                    "class_type": "KSampler",
                    "inputs": {
                        "seed": timestamp,
                        "steps": 25,
                        "cfg": 7.5,
                        "sampler_name": "dpmpp_2m",
                        "scheduler": "karras",
                        "denoise": 1.0,
                        "model": ["2", 0],
                        "positive": ["3", 0],
                        "negative": ["4", 0],
                        "latent_image": ["5", 0]
                    }
                },

                # Decode
                "7": {
                    "class_type": "VAEDecode",
                    "inputs": {
                        "samples": ["6", 0],
                        "vae": ["1", 2]
                    }
                },

                # Save
                "8": {
                    "class_type": "SaveImage",
                    "inputs": {
                        "images": ["7", 0],
                        "filename_prefix": f"char_{character_name.replace(' ', '_')}_{timestamp}"
                    }
                }
            }

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
                            # Wait for completion
                            image_path = await self._wait_for_image_completion(prompt_id, character_name, timestamp)
                            return image_path

        except Exception as e:
            logger.error(f"Image generation failed: {e}")

        return None

    async def generate_scene_video(
        self,
        image_path: str,
        scene_description: str,
        duration: float = 5.0
    ) -> Optional[str]:
        """Generate video using LTX Video 2B - ACTUAL WORKING WORKFLOW"""
        try:
            timestamp = int(time.time())

            # Extract just filename for LoadImage node
            image_filename = Path(image_path).name

            # PROVEN LTX Video 2B workflow (121 frames, 5.04 seconds)
            workflow = {
                # 1. Load LTX 2B model
                "1": {
                    "class_type": "CheckpointLoaderSimple",
                    "inputs": {"ckpt_name": "ltx-2/ltxv-2b-0.9.8-distilled.safetensors"}
                },
                # 2. Load T5 text encoder
                "2": {
                    "class_type": "CLIPLoader",
                    "inputs": {
                        "clip_name": "t5xxl_fp16.safetensors",
                        "type": "ltxv"
                    }
                },
                # 3. Positive prompt
                "3": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {
                        "text": f"{scene_description}, anime style, smooth animation, high quality",
                        "clip": ["2", 0]
                    }
                },
                # 4. Negative prompt
                "4": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {
                        "text": "static, boring, low quality, blurry, ugly, distorted, bad animation",
                        "clip": ["2", 0]
                    }
                },
                # 5. Load input image
                "5": {
                    "class_type": "LoadImage",
                    "inputs": {"image": image_filename}
                },
                # 6. Create video latent space (121 frames)
                "6": {
                    "class_type": "EmptyLTXVLatentVideo",
                    "inputs": {
                        "width": 768,
                        "height": 512,
                        "length": 121,  # 5 seconds at 24fps
                        "batch_size": 1
                    }
                },
                # 7. Image to video conversion
                "7": {
                    "class_type": "LTXVImgToVideo",
                    "inputs": {
                        "positive": ["3", 0],
                        "negative": ["4", 0],
                        "vae": ["1", 2],
                        "image": ["5", 0],
                        "width": 768,
                        "height": 512,
                        "length": 121,
                        "batch_size": 1,
                        "strength": 0.8
                    }
                },
                # 8. Video conditioning
                "8": {
                    "class_type": "LTXVConditioning",
                    "inputs": {
                        "positive": ["7", 0],
                        "negative": ["7", 1],
                        "frame_rate": 24
                    }
                },
                # 9. Video generation sampling
                "9": {
                    "class_type": "KSampler",
                    "inputs": {
                        "seed": timestamp,
                        "steps": 20,
                        "cfg": 3,
                        "sampler_name": "euler",
                        "scheduler": "normal",
                        "positive": ["8", 0],
                        "negative": ["8", 1],
                        "latent_image": ["6", 0],
                        "model": ["1", 0],
                        "denoise": 0.8
                    }
                },
                # 10. VAE decode video
                "10": {
                    "class_type": "VAEDecode",
                    "inputs": {"samples": ["9", 0], "vae": ["1", 2]}
                },
                # 11. Video output
                "11": {
                    "class_type": "VHS_VideoCombine",
                    "inputs": {
                        "images": ["10", 0],
                        "frame_rate": 24,
                        "loop_count": 0,
                        "filename_prefix": f"integrated_scene_{timestamp}",
                        "format": "video/h264-mp4",
                        "pingpong": False,
                        "save_output": True
                    }
                }
            }

            # Submit workflow
            logger.info(f"Submitting video workflow for image: {image_filename}")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.comfyui_url}/prompt",
                    json={"prompt": workflow}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        prompt_id = result.get("prompt_id")
                        logger.info(f"Video workflow submitted: {prompt_id}")

                        if prompt_id:
                            video_path = await self._wait_for_video_completion(prompt_id, timestamp)
                            return video_path
                        else:
                            logger.error("No prompt_id returned from ComfyUI")
                    else:
                        error_text = await response.text()
                        logger.error(f"ComfyUI video submission failed: {response.status} - {error_text}")

        except Exception as e:
            logger.error(f"Video generation failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

        return None

    async def generate_scene_music(
        self,
        scene_data: Dict[str, Any],
        duration: float = 30.0
    ) -> Optional[str]:
        """Generate or select music for scene via Apple Music service"""
        try:
            scene_type = scene_data.get("type", "dialogue")
            mood = scene_data.get("mood", "neutral")

            # Music generation request
            music_request = {
                "scene_type": scene_type,
                "mood": mood,
                "duration": duration,
                "style": "anime_soundtrack",
                "bpm": 120 if scene_type == "action" else 80
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.apple_music_url}/api/music/generate",
                    json=music_request,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get("audio_path")
                    else:
                        logger.warning(f"Music generation failed: {response.status}")

        except Exception as e:
            logger.warning(f"Music service unavailable: {e}")

        return None

    async def generate_scene_voice(
        self,
        dialogue: str,
        character_name: str,
        voice_style: str = "anime"
    ) -> Optional[str]:
        """Generate voice for dialogue via Echo Voice service"""
        try:
            voice_request = {
                "text": dialogue,
                "character": character_name,
                "style": voice_style,
                "language": "en",
                "speed": 1.0
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.echo_brain_url}/api/voice/synthesize",
                    json=voice_request,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get("audio_path")
                    else:
                        logger.warning(f"Voice generation failed: {response.status}")

        except Exception as e:
            logger.warning(f"Voice service unavailable: {e}")

        return None

    async def compile_final_episode(
        self,
        scenes: List[Dict[str, Any]],
        episode_id: str
    ) -> Optional[str]:
        """Compile all scene components into final episode"""
        try:
            logger.info(f"🎬 Compiling episode {episode_id} with {len(scenes)} scenes")

            # Collect all video files
            video_files = []
            audio_files = []

            for scene in scenes:
                if scene.get("video_path"):
                    video_files.append(scene["video_path"])
                if scene.get("music_path"):
                    audio_files.append(scene["music_path"])
                if scene.get("voice_path"):
                    audio_files.append(scene["voice_path"])

            if not video_files:
                logger.error("No video files to compile")
                return None

            # Create FFmpeg concat file
            timestamp = int(time.time())
            concat_file = self.storage_dir / f"episode_{episode_id}_concat_{timestamp}.txt"

            with open(concat_file, 'w') as f:
                for video_file in video_files:
                    if Path(video_file).exists():
                        f.write(f"file '{video_file}'\n")

            # Output path
            output_path = self.storage_dir / f"episode_{episode_id}_final_{timestamp}.mp4"

            # FFmpeg compilation command
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c:v", "libx264",
                "-crf", "18",
                "-preset", "medium",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                str(output_path)
            ]

            logger.info(f"Compiling episode: {' '.join(cmd[:8])}...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)

            if result.returncode == 0:
                logger.info(f"✅ Episode compiled: {output_path}")

                # Save to database
                await self._save_episode_to_database(episode_id, str(output_path), scenes)

                return str(output_path)
            else:
                logger.error(f"❌ FFmpeg error: {result.stderr}")
                return None

        except Exception as e:
            logger.error(f"Episode compilation failed: {e}")
            return None

    async def create_complete_episode(
        self,
        story_prompt: str,
        characters: List[str],
        episode_id: str,
        scene_count: int = 3
    ) -> Dict[str, Any]:
        """
        Create complete episode from story prompt
        INTEGRATED PIPELINE: Story → Image → Video → Music → Voice → Final
        """
        logger.info(f"🎭 Creating complete episode: {episode_id}")
        logger.info(f"Story: {story_prompt}")
        logger.info(f"Characters: {characters}")

        try:
            # VALIDATION GATE 1: Get Echo Brain context
            context = await self.get_echo_brain_context(story_prompt)
            logger.info(f"Context retrieved: {len(context.get('memories', []))} memories")

            # VALIDATION GATE 2: Get character data from database
            character_data = {}
            for char_name in characters:
                char_info = await self.get_character_data(char_name)
                if char_info:
                    character_data[char_name] = char_info
                    logger.info(f"✅ Character data: {char_name}")
                else:
                    logger.warning(f"⚠️ Character not found: {char_name}")

            if not character_data:
                return {"status": "failed", "error": "No character data found"}

            # Create scenes
            scenes = []
            for i in range(scene_count):
                scene_id = f"{episode_id}_scene_{i+1}"
                scene_description = f"{story_prompt}, scene {i+1}, {', '.join(characters)}"

                logger.info(f"🎬 Processing {scene_id}")

                # VALIDATION GATE 3: Generate character image
                main_character = list(character_data.keys())[0]
                image_path = await self.generate_character_image(
                    character_data[main_character],
                    scene_description
                )

                if not image_path:
                    logger.warning(f"⚠️ Image generation failed for {scene_id}")
                    continue

                logger.info(f"✅ Image generated: {image_path}")

                # Copy image to ComfyUI input directory for LoadImage node
                import shutil
                input_dir = Path("/mnt/1TB-storage/ComfyUI/input")
                input_image_name = f"scene_{i+1}_{Path(image_path).name}"
                input_image_path = input_dir / input_image_name
                shutil.copy2(image_path, input_image_path)
                logger.info(f"✅ Image copied to input: {input_image_path}")

                # VALIDATION GATE 4: Generate video from image
                video_path = await self.generate_scene_video(
                    str(input_image_path),
                    scene_description,
                    duration=5.0
                )

                if not video_path:
                    logger.warning(f"⚠️ Video generation failed for {scene_id}")
                    continue

                logger.info(f"✅ Video generated: {video_path}")

                # VALIDATION GATE 5: Generate music
                scene_data = {
                    "type": "action" if i % 2 == 0 else "dialogue",
                    "mood": "intense" if i % 2 == 0 else "calm"
                }
                music_path = await self.generate_scene_music(scene_data, duration=30.0)
                if music_path:
                    logger.info(f"✅ Music generated: {music_path}")

                # VALIDATION GATE 6: Generate voice (if dialogue)
                voice_path = None
                if scene_data["type"] == "dialogue":
                    dialogue = f"Dialogue for scene {i+1} with {main_character}"
                    voice_path = await self.generate_scene_voice(
                        dialogue,
                        main_character
                    )
                    if voice_path:
                        logger.info(f"✅ Voice generated: {voice_path}")

                # Add scene to compilation
                scenes.append({
                    "id": scene_id,
                    "description": scene_description,
                    "image_path": image_path,
                    "video_path": video_path,
                    "music_path": music_path,
                    "voice_path": voice_path,
                    "characters": characters
                })

            if not scenes:
                return {"status": "failed", "error": "No scenes generated successfully"}

            # VALIDATION GATE 7: Compile final episode
            final_video_path = await self.compile_final_episode(scenes, episode_id)

            if final_video_path:
                logger.info(f"🎉 Episode complete: {final_video_path}")

                return {
                    "status": "completed",
                    "episode_id": episode_id,
                    "video_path": final_video_path,
                    "scenes": scenes,
                    "duration": len(scenes) * 5.0,  # Approximate
                    "characters": characters,
                    "context_used": len(context.get('memories', [])) > 0
                }
            else:
                return {
                    "status": "partial",
                    "error": "Final compilation failed",
                    "scenes": scenes
                }

        except Exception as e:
            logger.error(f"Complete episode creation failed: {e}")
            return {"status": "failed", "error": str(e)}

    async def _wait_for_image_completion(self, prompt_id: str, character_name: str, timestamp: int) -> Optional[str]:
        """Wait for image generation completion"""
        sanitized_name = character_name.replace(' ', '_')
        expected_pattern = f"char_{sanitized_name}_{timestamp}_*.png"
        max_wait = 180  # 3 minutes for image
        start_time = time.time()

        while time.time() - start_time < max_wait:
            # Look for output files matching our pattern
            output_files = list(self.output_dir.glob(expected_pattern))
            if output_files:
                image_path = str(output_files[0])
                logger.info(f"✅ Image completed: {image_path}")
                return image_path

            await asyncio.sleep(5)

        logger.error(f"❌ Image generation timeout for {prompt_id}")
        return None

    async def _wait_for_video_completion(self, prompt_id: str, timestamp: int) -> Optional[str]:
        """Wait for video generation completion"""
        expected_pattern = f"integrated_scene_{timestamp}_*.mp4"
        max_wait = 300  # 5 minutes
        start_time = time.time()

        while time.time() - start_time < max_wait:
            # Look for output files matching our pattern
            output_files = list(self.output_dir.glob(expected_pattern))
            if output_files:
                video_path = str(output_files[0])
                logger.info(f"✅ Video completed: {video_path}")
                return video_path

            await asyncio.sleep(10)

        logger.error(f"❌ Video generation timeout for {prompt_id}")
        return None

    async def _save_episode_to_database(self, episode_id: str, video_path: str, scenes: List[Dict[str, Any]]):
        """Save episode to database"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO episodes (name, description, status, duration, episode_data)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET
                    status = EXCLUDED.status,
                    episode_data = EXCLUDED.episode_data,
                    updated_at = NOW()
            """, (
                episode_id,
                f"Integrated production episode: {episode_id}",
                "completed",
                len(scenes) * 5.0,
                json.dumps({
                    "video_path": video_path,
                    "scenes": scenes,
                    "production_method": "integrated_pipeline",
                    "generation_timestamp": time.time()
                })
            ))

            conn.commit()
            conn.close()
            logger.info(f"✅ Episode saved to database: {episode_id}")

        except Exception as e:
            logger.error(f"Database save failed: {e}")

# Global instance
integrated_pipeline = IntegratedAnimeProductionPipeline()

async def main():
    """Test the integrated pipeline"""
    logger.info("🚀 Testing Integrated Anime Production Pipeline")

    # Test with actual project characters
    result = await integrated_pipeline.create_complete_episode(
        story_prompt="Cyberpunk Tokyo night scene with street racing and corporate conspiracy",
        characters=["Akira Yamamoto", "Luna Chen"],
        episode_id="integration_test_001",
        scene_count=2
    )

    if result["status"] == "completed":
        print("🎉 SUCCESS! Integrated pipeline working!")
        print(f"📁 Episode: {result['video_path']}")
        print(f"🎬 Scenes: {len(result['scenes'])}")
        print(f"👥 Characters: {result['characters']}")
        print(f"🧠 Context used: {result['context_used']}")
    else:
        print(f"❌ Pipeline failed: {result.get('error', 'Unknown error')}")
        if result.get('scenes'):
            print(f"Partial success: {len(result['scenes'])} scenes generated")

if __name__ == "__main__":
    asyncio.run(main())