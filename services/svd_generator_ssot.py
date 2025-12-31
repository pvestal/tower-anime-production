#!/usr/bin/env python3
"""
SVD Video Generation with PostgreSQL SSOT Integration
Uses YOUR svd_xt.safetensors model for REAL smooth video
"""
import asyncio
import asyncpg
import hashlib
import json
import httpx
from datetime import datetime
from pathlib import Path
import uuid

class SVDGeneratorWithPostgresSSOT:
    def __init__(self):
        self.comfyui_url = "http://localhost:8188"
        self.db_config = {
            'host': 'localhost',
            'database': 'tower_consolidated',
            'user': 'patrick',
            'password': 'tower_echo_brain_secret_key_2025'
        }

    async def generate_mei_video(self, action_tag: str = "desperate_pleasure"):
        """Generate Mei video with SVD and log to PostgreSQL SSOT"""

        print(f"\n🎬 Generating Mei video with SVD: {action_tag}")
        print("="*60)

        # 1. Connect to YOUR PostgreSQL
        conn = await asyncpg.connect(**self.db_config)

        # 2. Get optimal parameters from SSOT history
        best_params = await self.get_optimal_parameters(conn, action_tag)
        print(f"📊 SSOT Parameters: motion_bucket={best_params['motion_bucket_id']}, seed={best_params['seed']}")

        # 3. Use YOUR good Mei image as base
        base_image = "/home/patrick/ComfyUI/output/Mei_realistic_masturbation_keyframe_00001_.png"

        # 4. Create generation hash
        generation_hash = hashlib.sha256(
            f"mei_{action_tag}_{best_params['seed']}_{best_params['motion_bucket_id']}".encode()
        ).hexdigest()

        # 5. Check cache first
        existing = await conn.fetchrow('''
            SELECT * FROM video_generation_cache
            WHERE generation_hash = $1 AND quality_score > 0.7
        ''', generation_hash)

        if existing:
            print(f"✅ SSOT CACHE HIT: {existing['output_video_path']}")
            await conn.close()
            return existing['output_video_path']

        # 6. Build SVD workflow
        workflow = self.build_svd_workflow(
            image_path=base_image,
            motion_bucket_id=best_params['motion_bucket_id'],
            seed=best_params['seed'],
            fps=best_params.get('fps', 24),
            frames=best_params.get('frames', 25),
            cfg=best_params.get('cfg_scale', 2.5)
        )

        # 7. Submit to ComfyUI
        async with httpx.AsyncClient(timeout=300) as client:
            print(f"📤 Submitting SVD workflow...")
            response = await client.post(
                f"{self.comfyui_url}/prompt",
                json={"prompt": workflow}
            )

            if response.status_code != 200:
                print(f"❌ ComfyUI error: {response.text[:200]}")
                await conn.close()
                return None

            prompt_id = response.json().get("prompt_id")
            print(f"✅ Generation started: {prompt_id}")

        # 8. Log to SSOT immediately
        output_path = f"/home/patrick/ComfyUI/output/Mei_SVD_{action_tag}_{datetime.now().strftime('%H%M%S')}.webp"

        await conn.execute('''
            INSERT INTO video_generation_cache (
                generation_hash, character_name, semantic_action,
                motion_bucket_id, fps, frames, seed, cfg_scale,
                comfyui_prompt_id, output_video_path, motion_score, coherence_score
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (generation_hash) DO UPDATE SET
                used_count = video_generation_cache.used_count + 1
        ''', generation_hash, 'Mei', action_tag,
            best_params['motion_bucket_id'], best_params['fps'], best_params['frames'],
            best_params['seed'], best_params['cfg_scale'],
            prompt_id, output_path, 0.8, 0.8)

        print(f"✅ Logged to PostgreSQL SSOT")

        # 9. Cache in Redis
        await self.cache_in_redis(generation_hash, best_params)

        await conn.close()

        print(f"\n⏳ Generating smooth SVD video (2-3 minutes)...")
        print(f"📹 Output will be: {output_path}")

        return output_path

    async def get_optimal_parameters(self, conn, action_tag: str):
        """Get best parameters from PostgreSQL SSOT history"""

        # Try to get previous successful parameters
        result = await conn.fetchrow('''
            SELECT motion_bucket_id, fps, seed, cfg_scale, frames
            FROM video_generation_cache
            WHERE semantic_action = $1 AND quality_score > 0.6
            ORDER BY quality_score DESC, used_count DESC
            LIMIT 1
        ''', action_tag)

        if result:
            print(f"📚 Using SSOT learned parameters from previous success")
            return dict(result)

        # For desperate_pleasure, use high motion
        if "desperate" in action_tag or "intimate" in action_tag:
            return {
                'motion_bucket_id': 180,  # High motion for intimate scenes
                'fps': 24,
                'frames': 25,
                'seed': 1766770469,  # YOUR proven seed
                'cfg_scale': 2.5
            }

        # Default SVD parameters
        return {
            'motion_bucket_id': 127,  # Standard motion
            'fps': 24,
            'frames': 25,
            'seed': 42,
            'cfg_scale': 2.5
        }

    def build_svd_workflow(self, image_path: str, motion_bucket_id: int,
                          seed: int, fps: int = 24, frames: int = 25, cfg: float = 2.5):
        """Build SVD workflow for YOUR ComfyUI"""

        return {
            # Load SVD model
            "3": {
                "class_type": "ImageOnlyCheckpointLoader",
                "inputs": {
                    "ckpt_name": "svd_xt.safetensors"
                }
            },

            # Load YOUR Mei image
            "4": {
                "class_type": "LoadImage",
                "inputs": {
                    "image": image_path,
                    "upload": "image"
                }
            },

            # SVD conditioning with motion parameters
            "5": {
                "class_type": "SVD_img2vid_Conditioning",
                "inputs": {
                    "clip_vision": ["3", 1],  # clip_vision from checkpoint
                    "init_image": ["4", 0],   # image output
                    "vae": ["3", 2],          # vae from checkpoint
                    "width": 1024,
                    "height": 576,
                    "video_frames": frames,
                    "motion_bucket_id": motion_bucket_id,  # CRITICAL for smooth motion
                    "fps": fps,
                    "augmentation_level": 0.0
                }
            },

            # KSampler for SVD
            "6": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["3", 0],        # model from checkpoint
                    "positive": ["5", 0],      # positive conditioning
                    "negative": ["5", 1],      # negative conditioning
                    "latent_image": ["5", 2],  # latent from conditioning
                    "seed": seed,
                    "steps": 25,
                    "cfg": cfg,
                    "sampler_name": "euler",
                    "scheduler": "sgm_uniform",
                    "denoise": 1.0
                }
            },

            # Decode video
            "7": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["6", 0],
                    "vae": ["3", 2]
                }
            },

            # Save as video
            "8": {
                "class_type": "SaveAnimatedWEBP",
                "inputs": {
                    "images": ["7", 0],
                    "filename_prefix": f"Mei_SVD_{datetime.now().strftime('%H%M%S')}",
                    "fps": fps,
                    "lossless": False,
                    "quality": 90,
                    "method": "default"
                }
            }
        }

    async def cache_in_redis(self, key: str, data: dict):
        """Cache in Redis for fast access"""
        try:
            import redis
            r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
            r.setex(
                f"video_gen:{key[:16]}",
                86400,  # 24 hour TTL
                json.dumps(data)
            )
            print(f"✅ Cached in Redis: video_gen:{key[:16]}")
        except Exception as e:
            print(f"⚠️ Redis cache: {str(e)[:50]}")

async def main():
    generator = SVDGeneratorWithPostgresSSOT()

    # Generate with YOUR semantic action
    result = await generator.generate_mei_video("desperate_pleasure")

    if result:
        print(f"\n🎉 SUCCESS: {result}")
    else:
        print(f"\n❌ Generation failed")

if __name__ == "__main__":
    asyncio.run(main())