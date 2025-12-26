#!/usr/bin/env python3
"""
Fixed Job Tracker with Database Persistence
Replaces the in-memory job storage with proper PostgreSQL persistence
"""

import psycopg2
import json
from datetime import datetime
from typing import Dict, List, Optional
import uuid
import logging

logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "database": "anime_production",
    "user": "patrick",
    "password": "tower_echo_brain_secret_key_2025"
}

class JobTracker:
    """Database-backed job tracking system"""

    def __init__(self):
        self.db_config = DB_CONFIG

    def get_connection(self):
        """Get database connection"""
        return psycopg2.connect(**self.db_config)

    def create_video_job(self, job_data: Dict) -> str:
        """Create a new video generation job"""
        job_id = job_data.get('job_id', str(uuid.uuid4()))

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO video_generations (
                        job_id, prompt, num_frames, fps, width, height,
                        workflow_type, status, settings, comfyui_prompt_id,
                        total_frames, created_at, started_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    job_id,
                    job_data.get('prompt', ''),
                    job_data.get('num_frames', 48),
                    job_data.get('fps', 24),
                    job_data.get('width', 512),
                    job_data.get('height', 512),
                    job_data.get('workflow_type', 'video'),
                    'pending',
                    json.dumps(job_data.get('settings', {})),
                    job_data.get('comfyui_prompt_id'),
                    job_data.get('num_frames', 48),
                    datetime.now(),
                    datetime.now()
                ))
                conn.commit()

        logger.info(f"Created video job {job_id} in database")
        return job_id

    def create_image_job(self, job_data: Dict) -> str:
        """Create a new image generation job"""
        job_id = job_data.get('job_id', str(uuid.uuid4()))

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO character_generations (
                        id, character_name, prompt, negative_prompt, model_name,
                        workflow_type, status, settings, comfyui_prompt_id,
                        created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    job_id,
                    job_data.get('character_name', 'default'),
                    job_data.get('prompt', ''),
                    job_data.get('negative_prompt', 'worst quality, low quality'),
                    job_data.get('model_name', 'AOM3A1B.safetensors'),
                    job_data.get('workflow_type', 'image'),
                    'pending',
                    json.dumps(job_data.get('settings', {})),
                    job_data.get('comfyui_prompt_id'),
                    datetime.now()
                ))
                conn.commit()

        logger.info(f"Created image job {job_id} in database")
        return job_id

    def update_job(self, job_id: str, data: Dict):
        """Update job with data - simple in-memory tracking for images"""
        # For now, just log it
        logger.info(f"Job {job_id}: {data}")
        return True

    def update_job_status(self, job_id: str, status: str, progress: int = None,
                         current_frame: int = None, output_path: str = None,
                         error_message: str = None):
        """Update job status in database"""

        # Try video_generations table first
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Check if it's a video job
                cur.execute("SELECT id FROM video_generations WHERE job_id = %s", (job_id,))
                if cur.fetchone():
                    update_fields = ["status = %s", "updated_at = %s"]
                    values = [status, datetime.now()]

                    if progress is not None:
                        update_fields.append("progress = %s")
                        values.append(progress)

                    if current_frame is not None:
                        update_fields.append("current_frame = %s")
                        values.append(current_frame)

                    if output_path is not None:
                        update_fields.append("output_path = %s")
                        values.append(output_path)

                    if error_message is not None:
                        update_fields.append("error_message = %s")
                        values.append(error_message)

                    if status == 'completed':
                        update_fields.append("completed_at = %s")
                        values.append(datetime.now())

                    values.append(job_id)  # for WHERE clause

                    cur.execute(f"""
                        UPDATE video_generations
                        SET {', '.join(update_fields)}
                        WHERE job_id = %s
                    """, values)
                    conn.commit()
                    logger.info(f"Updated video job {job_id}: {status}")
                    return

                # Check if it's an image job
                cur.execute("SELECT id FROM character_generations WHERE id = %s", (job_id,))
                if cur.fetchone():
                    update_fields = ["status = %s"]
                    values = [status]

                    if output_path is not None:
                        update_fields.append("output_path = %s")
                        values.append(output_path)

                    if error_message is not None:
                        update_fields.append("error_message = %s")
                        values.append(error_message)

                    if status == 'completed':
                        update_fields.append("completed_at = %s")
                        values.append(datetime.now())

                    values.append(job_id)  # for WHERE clause

                    cur.execute(f"""
                        UPDATE character_generations
                        SET {', '.join(update_fields)}
                        WHERE id = %s
                    """, values)
                    conn.commit()
                    logger.info(f"Updated image job {job_id}: {status}")
                    return

        logger.warning(f"Job {job_id} not found in database")

    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get job details from database"""

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Try video_generations first
                cur.execute("""
                    SELECT job_id, prompt, status, progress, current_frame, total_frames,
                           output_path, error_message, created_at, completed_at,
                           comfyui_prompt_id, generation_time, workflow_type
                    FROM video_generations WHERE job_id = %s
                """, (job_id,))

                row = cur.fetchone()
                if row:
                    return {
                        'job_id': row[0],
                        'prompt': row[1],
                        'status': row[2],
                        'progress': row[3] or 0,
                        'current_frame': row[4] or 0,
                        'total_frames': row[5] or 48,
                        'output_path': row[6],
                        'error_message': row[7],
                        'created_at': row[8].isoformat() if row[8] else None,
                        'completed_at': row[9].isoformat() if row[9] else None,
                        'comfyui_prompt_id': row[10],
                        'generation_time': row[11],
                        'type': 'video',
                        'workflow_type': row[12]
                    }

                # Try character_generations
                cur.execute("""
                    SELECT id, character_name, prompt, status, output_path, error_message,
                           created_at, completed_at, comfyui_prompt_id, workflow_type
                    FROM character_generations WHERE id = %s
                """, (job_id,))

                row = cur.fetchone()
                if row:
                    return {
                        'job_id': row[0],
                        'character_name': row[1],
                        'prompt': row[2],
                        'status': row[3],
                        'output_path': row[4],
                        'error_message': row[5],
                        'created_at': row[6].isoformat() if row[6] else None,
                        'completed_at': row[7].isoformat() if row[7] else None,
                        'comfyui_prompt_id': row[8],
                        'type': 'image',
                        'workflow_type': row[9]
                    }

        return None

    def list_jobs(self, limit: int = 50, status: str = None) -> List[Dict]:
        """List jobs from database"""
        jobs = []

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Get video jobs
                where_clause = ""
                params = []
                if status:
                    where_clause = "WHERE status = %s"
                    params.append(status)

                cur.execute(f"""
                    SELECT job_id, prompt, status, progress, created_at, workflow_type
                    FROM video_generations {where_clause}
                    ORDER BY created_at DESC LIMIT %s
                """, params + [limit])

                for row in cur.fetchall():
                    jobs.append({
                        'job_id': row[0],
                        'prompt': row[1],
                        'status': row[2],
                        'progress': row[3] or 0,
                        'created_at': row[4].isoformat() if row[4] else None,
                        'type': 'video',
                        'workflow_type': row[5]
                    })

                # Get image jobs
                cur.execute(f"""
                    SELECT id, character_name, prompt, status, created_at, workflow_type
                    FROM character_generations {where_clause}
                    ORDER BY created_at DESC LIMIT %s
                """, params + [limit])

                for row in cur.fetchall():
                    jobs.append({
                        'job_id': row[0],
                        'character_name': row[1],
                        'prompt': row[2],
                        'status': row[3],
                        'created_at': row[4].isoformat() if row[4] else None,
                        'type': 'image',
                        'workflow_type': row[5]
                    })

        # Sort by created_at descending
        jobs.sort(key=lambda x: x['created_at'] or '', reverse=True)
        return jobs[:limit]

    def count_total_jobs(self) -> int:
        """Count total number of jobs across both tables"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()

                # Count video jobs
                cur.execute("SELECT COUNT(*) FROM video_generations")
                video_count = cur.fetchone()[0] or 0

                # Count image jobs
                cur.execute("SELECT COUNT(*) FROM character_generations")
                image_count = cur.fetchone()[0] or 0

                return video_count + image_count
        except Exception as e:
            logger.error(f"Failed to count total jobs: {e}")
            return 0

    def count_jobs_by_status(self, status: str) -> int:
        """Count jobs with specific status"""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()

                # Count video jobs with status
                cur.execute("SELECT COUNT(*) FROM video_generations WHERE status = %s", (status,))
                video_count = cur.fetchone()[0] or 0

                # Count image jobs with status
                cur.execute("SELECT COUNT(*) FROM character_generations WHERE status = %s", (status,))
                image_count = cur.fetchone()[0] or 0

                return video_count + image_count
        except Exception as e:
            logger.error(f"Failed to count jobs by status: {e}")
            return 0


# Global job tracker instance
job_tracker = JobTracker()