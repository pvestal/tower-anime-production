#!/usr/bin/env python3
"""
Generation Cache Manager - Rapid Regeneration & Intelligent Reuse System
Handles caching, retrieval, and optimization of anime generations
"""

import os
import json
import hashlib
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from uuid import uuid4
import psycopg2
from psycopg2.extras import RealDictCursor, Json
import aiofiles
import httpx
import numpy as np
from PIL import Image
import cv2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GenerationCacheManager:
    """Manages the generation cache for rapid regeneration and reuse"""

    def __init__(self):
        self.db_config = {
            'host': 'localhost',
            'database': 'tower_consolidated',
            'user': 'patrick',
            'password': 'tower_echo_brain_secret_key_2025'
        }
        self.cache_dir = Path('/opt/tower-anime-production/cache')
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnails_dir = self.cache_dir / 'thumbnails'
        self.thumbnails_dir.mkdir(exist_ok=True)

    def connect_db(self):
        """Establish database connection"""
        return psycopg2.connect(**self.db_config)

    def generate_cache_key(self, params: Dict[str, Any]) -> str:
        """Generate unique cache key from generation parameters"""
        # Sort parameters for consistent hashing
        sorted_params = json.dumps(params, sort_keys=True)
        return hashlib.sha256(sorted_params.encode()).hexdigest()

    async def check_cache(self,
                         character_id: int,
                         action_id: int,
                         style_id: Optional[int] = None,
                         similarity_threshold: float = 0.95) -> Optional[Dict[str, Any]]:
        """
        Check if a similar generation exists in cache
        Returns the best matching cached result if found
        """
        conn = self.connect_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # First try exact match
            query = """
                SELECT * FROM generation_cache
                WHERE character_id = %s
                AND action_id = %s
                AND quality_score > %s
            """
            params = [character_id, action_id, similarity_threshold]

            if style_id:
                query += " AND style_angle_id = %s"
                params.append(style_id)

            query += " ORDER BY quality_score DESC, created_at DESC LIMIT 1"

            cur.execute(query, params)
            exact_match = cur.fetchone()

            if exact_match:
                # Update access count and timestamp
                cur.execute("""
                    UPDATE generation_cache
                    SET used_count = used_count + 1,
                        last_accessed = NOW()
                    WHERE id = %s
                """, (exact_match['id'],))
                conn.commit()

                logger.info(f"Cache hit! Found exact match with quality {exact_match['quality_score']}")
                return dict(exact_match)

            # If no exact match, try similar combinations
            cur.execute("""
                SELECT gc.*,
                       sa.action_tag,
                       sal.style_name,
                       COUNT(*) OVER() as similar_count
                FROM generation_cache gc
                JOIN semantic_actions sa ON gc.action_id = sa.id
                LEFT JOIN style_angle_library sal ON gc.style_angle_id = sal.id
                WHERE gc.character_id = %s
                AND sa.category = (
                    SELECT category FROM semantic_actions WHERE id = %s
                )
                AND gc.quality_score > %s
                ORDER BY gc.quality_score DESC
                LIMIT 5
            """, (character_id, action_id, similarity_threshold * 0.8))

            similar_matches = cur.fetchall()

            if similar_matches:
                best_match = similar_matches[0]
                logger.info(f"Found {best_match['similar_count']} similar generations")
                return dict(best_match)

            return None

        finally:
            cur.close()
            conn.close()

    async def store_generation(self,
                              generation_data: Dict[str, Any],
                              output_files: List[str],
                              quality_metrics: Dict[str, float]) -> str:
        """
        Store a new generation in the cache
        Returns the cache ID
        """
        conn = self.connect_db()
        cur = conn.cursor()

        try:
            # Calculate quality score
            quality_score = self.calculate_quality_score(quality_metrics)

            # Generate thumbnails
            thumbnails = await self.generate_thumbnails(output_files)

            # Calculate file sizes
            file_sizes = [Path(f).stat().st_size for f in output_files]

            # Generate output hash for deduplication
            output_hash = self.generate_output_hash(output_files)

            # Extract dimensions and video info
            dimensions, fps, frame_count = await self.extract_media_info(output_files[0])

            cache_id = str(uuid4())

            cur.execute("""
                INSERT INTO generation_cache (
                    id, character_id, action_id, style_angle_id,
                    workflow_template_id, positive_prompt, negative_prompt,
                    seed, cfg_scale, steps, sampler, scheduler,
                    base_model, lora_weights, controlnet_config,
                    motion_config, output_hash, output_paths,
                    thumbnails, file_sizes, dimensions, fps,
                    frame_count, quality_metrics, quality_score,
                    generation_time_ms, project_id, metadata
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                cache_id,
                generation_data.get('character_id'),
                generation_data.get('action_id'),
                generation_data.get('style_angle_id'),
                generation_data.get('workflow_template_id'),
                generation_data.get('positive_prompt'),
                generation_data.get('negative_prompt'),
                generation_data.get('seed'),
                generation_data.get('cfg_scale'),
                generation_data.get('steps'),
                generation_data.get('sampler'),
                generation_data.get('scheduler'),
                generation_data.get('base_model'),
                Json(generation_data.get('lora_weights', {})),
                Json(generation_data.get('controlnet_config', {})),
                Json(generation_data.get('motion_config', {})),
                output_hash,
                output_files,
                thumbnails,
                file_sizes,
                dimensions,
                fps,
                frame_count,
                Json(quality_metrics),
                quality_score,
                generation_data.get('generation_time_ms'),
                generation_data.get('project_id'),
                Json(generation_data.get('metadata', {}))
            ))

            conn.commit()
            logger.info(f"Cached generation {cache_id} with quality score {quality_score:.2f}")

            # Learn from high-quality generations
            if quality_score > 0.85:
                await self.learn_from_success(cache_id, generation_data, quality_metrics)

            return cache_id

        except Exception as e:
            logger.error(f"Failed to store generation: {e}")
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    def calculate_quality_score(self, metrics: Dict[str, float]) -> float:
        """
        Calculate overall quality score from individual metrics
        Weights: Motion 50%, Technical 20%, Consistency 20%, Duration 10%
        """
        weights = {
            'motion_quality': 0.5,
            'technical_quality': 0.2,
            'consistency_score': 0.2,
            'duration_accuracy': 0.1
        }

        score = 0.0
        for metric, weight in weights.items():
            if metric in metrics:
                score += metrics[metric] * weight

        return min(max(score, 0.0), 1.0)

    async def generate_thumbnails(self, output_files: List[str]) -> List[str]:
        """Generate thumbnail images for quick preview"""
        thumbnails = []

        for file_path in output_files:
            try:
                if file_path.endswith(('.mp4', '.webm', '.avi')):
                    # Extract first frame from video
                    cap = cv2.VideoCapture(file_path)
                    ret, frame = cap.read()
                    if ret:
                        thumb_path = self.thumbnails_dir / f"{Path(file_path).stem}_thumb.jpg"
                        # Resize to thumbnail
                        thumb = cv2.resize(frame, (256, 256))
                        cv2.imwrite(str(thumb_path), thumb)
                        thumbnails.append(str(thumb_path))
                    cap.release()
                elif file_path.endswith(('.png', '.jpg', '.jpeg')):
                    # Create thumbnail from image
                    img = Image.open(file_path)
                    img.thumbnail((256, 256))
                    thumb_path = self.thumbnails_dir / f"{Path(file_path).stem}_thumb.jpg"
                    img.save(thumb_path)
                    thumbnails.append(str(thumb_path))
            except Exception as e:
                logger.warning(f"Failed to generate thumbnail for {file_path}: {e}")

        return thumbnails

    def generate_output_hash(self, output_files: List[str]) -> str:
        """Generate hash of output files for deduplication"""
        hasher = hashlib.sha256()

        for file_path in sorted(output_files):
            try:
                with open(file_path, 'rb') as f:
                    # Read first and last 1MB for performance
                    hasher.update(f.read(1024 * 1024))
                    f.seek(-1024 * 1024, 2)
                    hasher.update(f.read())
            except:
                pass

        return hasher.hexdigest()

    async def extract_media_info(self, file_path: str) -> Tuple[str, int, int]:
        """Extract dimensions, fps, and frame count from media file"""
        try:
            if file_path.endswith(('.mp4', '.webm', '.avi')):
                cap = cv2.VideoCapture(file_path)
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = int(cap.get(cv2.CAP_PROP_FPS))
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                cap.release()
                return f"{width}x{height}", fps, frame_count
            elif file_path.endswith(('.png', '.jpg', '.jpeg')):
                img = Image.open(file_path)
                return f"{img.width}x{img.height}", 0, 1
        except Exception as e:
            logger.warning(f"Failed to extract media info: {e}")

        return "unknown", 0, 0

    async def learn_from_success(self,
                                cache_id: str,
                                generation_data: Dict[str, Any],
                                quality_metrics: Dict[str, float]):
        """Learn from successful generations to improve future ones"""
        conn = self.connect_db()
        cur = conn.cursor()

        try:
            # Analyze what made this generation successful
            insights = []

            if quality_metrics.get('motion_quality', 0) > 0.9:
                insights.append("High motion quality achieved with current motion_bucket_id")

            if quality_metrics.get('consistency_score', 0) > 0.9:
                insights.append("Excellent character consistency with this LoRA combination")

            # Store learnings
            for insight in insights:
                cur.execute("""
                    INSERT INTO generation_learnings (
                        cache_id, learning_type, insight,
                        parameters_changed, quality_delta
                    ) VALUES (%s, %s, %s, %s, %s)
                """, (
                    cache_id, 'success', insight,
                    Json({}), 0.0
                ))

            # Update workflow template success rate
            if generation_data.get('workflow_template_id'):
                cur.execute("""
                    UPDATE workflow_templates
                    SET success_rate = success_rate * 0.95 + %s * 0.05
                    WHERE id = %s
                """, (
                    quality_metrics.get('overall_score', 0),
                    generation_data['workflow_template_id']
                ))

            conn.commit()

        except Exception as e:
            logger.error(f"Failed to learn from success: {e}")
            conn.rollback()
        finally:
            cur.close()
            conn.close()

    async def rapid_regenerate(self,
                              cache_id: str,
                              modifications: Dict[str, Any]) -> Dict[str, Any]:
        """
        Rapidly regenerate from a cached result with modifications
        This is the core of the "Rapid Regeneration" feature
        """
        conn = self.connect_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Fetch the original cached generation
            cur.execute("SELECT * FROM generation_cache WHERE id = %s", (cache_id,))
            original = cur.fetchone()

            if not original:
                raise ValueError(f"Cache ID {cache_id} not found")

            # Create new generation config by merging modifications
            new_config = dict(original)
            new_config.update(modifications)

            # Update seed if not specified to get variation
            if 'seed' not in modifications:
                new_config['seed'] = original['seed'] + 1

            logger.info(f"Rapid regeneration from {cache_id} with modifications: {modifications.keys()}")

            return new_config

        finally:
            cur.close()
            conn.close()

    async def get_best_recipe(self,
                             character_id: int,
                             action_id: int,
                             style_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Get the best generation recipe for a character/action/style combo
        This enables instant "best known configuration" retrieval
        """
        conn = self.connect_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            cur.execute("SELECT * FROM get_regeneration_recipe(%s, %s, %s)",
                       (character_id, action_id, style_id))

            result = cur.fetchone()
            if result:
                logger.info(f"Found best recipe with quality score {result['quality_score']}")
                return dict(result)

            return None

        finally:
            cur.close()
            conn.close()

    async def cleanup_old_cache(self, days_old: int = 30):
        """Clean up old, unused cache entries"""
        conn = self.connect_db()
        cur = conn.cursor()

        try:
            # Delete old entries with low quality and no recent use
            cur.execute("""
                DELETE FROM generation_cache
                WHERE created_at < NOW() - INTERVAL '%s days'
                AND quality_score < 0.5
                AND used_count < 2
                AND last_accessed < NOW() - INTERVAL '7 days'
            """, (days_old,))

            deleted = cur.rowcount
            conn.commit()

            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old cache entries")

            # Also clean up orphaned thumbnails
            await self.cleanup_orphaned_thumbnails()

        finally:
            cur.close()
            conn.close()

    async def cleanup_orphaned_thumbnails(self):
        """Remove thumbnail files that no longer have cache entries"""
        conn = self.connect_db()
        cur = conn.cursor()

        try:
            # Get all valid thumbnail paths
            cur.execute("SELECT unnest(thumbnails) as thumb FROM generation_cache")
            valid_thumbs = {row[0] for row in cur.fetchall()}

            # Check filesystem
            for thumb_file in self.thumbnails_dir.glob("*.jpg"):
                if str(thumb_file) not in valid_thumbs:
                    thumb_file.unlink()
                    logger.debug(f"Removed orphaned thumbnail: {thumb_file}")

        finally:
            cur.close()
            conn.close()

    async def get_cache_statistics(self) -> Dict[str, Any]:
        """Get statistics about cache usage and performance"""
        conn = self.connect_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            stats = {}

            # Overall statistics
            cur.execute("""
                SELECT
                    COUNT(*) as total_cached,
                    AVG(quality_score) as avg_quality,
                    SUM(used_count) as total_reuses,
                    SUM(array_length(file_sizes, 1)) as total_files,
                    AVG(generation_time_ms) as avg_generation_time
                FROM generation_cache
            """)
            stats['overall'] = dict(cur.fetchone())

            # Top performing combinations
            cur.execute("""
                SELECT * FROM top_generation_combos LIMIT 10
            """)
            stats['top_combinations'] = [dict(row) for row in cur.fetchall()]

            # Cache hit rate (last 24 hours)
            cur.execute("""
                SELECT
                    COUNT(CASE WHEN used_count > 0 THEN 1 END)::FLOAT /
                    NULLIF(COUNT(*), 0) * 100 as hit_rate
                FROM generation_cache
                WHERE created_at > NOW() - INTERVAL '24 hours'
            """)
            stats['hit_rate_24h'] = cur.fetchone()['hit_rate'] or 0

            return stats

        finally:
            cur.close()
            conn.close()


class RapidGenerationOrchestrator:
    """Orchestrates rapid generation using the cache system"""

    def __init__(self):
        self.cache_manager = GenerationCacheManager()
        self.comfyui_api = "http://localhost:8188"

    async def generate_with_cache(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entry point for generation with intelligent caching
        """
        # Check cache first
        cached = await self.cache_manager.check_cache(
            character_id=request['character_id'],
            action_id=request['action_id'],
            style_id=request.get('style_id')
        )

        if cached and request.get('use_cache', True):
            # Rapid regenerate from cache
            if request.get('variations'):
                return await self.cache_manager.rapid_regenerate(
                    cached['id'],
                    request['variations']
                )
            return cached

        # No cache hit, generate new
        generation_result = await self.execute_generation(request)

        # Store in cache
        if generation_result['success']:
            cache_id = await self.cache_manager.store_generation(
                generation_data=request,
                output_files=generation_result['outputs'],
                quality_metrics=generation_result['metrics']
            )
            generation_result['cache_id'] = cache_id

        return generation_result

    async def execute_generation(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Execute actual generation via ComfyUI"""
        # This would integrate with your ComfyUI API
        # Placeholder for actual implementation
        return {
            'success': True,
            'outputs': [],
            'metrics': {
                'motion_quality': 0.0,
                'technical_quality': 0.0,
                'consistency_score': 0.0,
                'duration_accuracy': 0.0
            }
        }


if __name__ == "__main__":
    # Test the cache system
    async def test():
        manager = GenerationCacheManager()
        stats = await manager.get_cache_statistics()
        print(json.dumps(stats, indent=2))

    asyncio.run(test())