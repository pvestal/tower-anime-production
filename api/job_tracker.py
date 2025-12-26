#!/usr/bin/env python3
"""Job tracking service with proper database synchronization"""

import time
import json
import redis
import requests
import logging
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JobTracker:
    def __init__(self):
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0)
        self.comfyui_url = 'http://localhost:8188'
        self.db_config = {
            'host': 'localhost',
            'database': 'anime_production',
            'user': 'patrick',
            'password': 'tower_echo_brain_secret_key_2025'
        }

    def get_db_connection(self):
        return psycopg2.connect(**self.db_config, cursor_factory=RealDictCursor)

    def sync_comfyui_jobs(self):
        """Synchronize jobs between ComfyUI and database"""
        conn = self.get_db_connection()
        cur = conn.cursor()

        try:
            # Get pending/processing jobs
            cur.execute("""
                SELECT id, comfyui_prompt_id, status
                FROM video_generations
                WHERE status IN ('pending', 'processing')
                AND created_at > NOW() - INTERVAL '24 hours'
            """)
            jobs = cur.fetchall()

            if not jobs:
                return

            # Get ComfyUI history
            try:
                response = requests.get(f"{self.comfyui_url}/history", timeout=10)
                if response.status_code != 200:
                    logger.warning("Failed to get ComfyUI history")
                    return
                history = response.json()
            except Exception as e:
                logger.error(f"ComfyUI connection error: {e}")
                return

            # Update each job
            for job in jobs:
                if job['comfyui_prompt_id'] and job['comfyui_prompt_id'] in history:
                    prompt_data = history[job['comfyui_prompt_id']]
                    outputs = prompt_data.get('outputs', {})

                    # Check for completion
                    if outputs:
                        cur.execute("""
                            UPDATE video_generations
                            SET status = 'completed',
                                progress = 100,
                                completed_at = NOW(),
                                updated_at = NOW(),
                                outputs = %s
                            WHERE id = %s
                        """, (json.dumps(outputs), job['id']))
                        logger.info(f"Job {job['id']} completed")

            conn.commit()
            logger.info(f"Synced {len(jobs)} jobs")

        except Exception as e:
            logger.error(f"Sync error: {e}")
            conn.rollback()
        finally:
            cur.close()
            conn.close()

    def cleanup_stuck_jobs(self):
        """Clean up jobs stuck in processing state"""
        conn = self.get_db_connection()
        cur = conn.cursor()

        try:
            cur.execute("""
                UPDATE video_generations
                SET status = 'failed',
                    error_message = 'Job timed out',
                    completed_at = NOW()
                WHERE status = 'processing'
                AND started_at < NOW() - INTERVAL '1 hour'
            """)

            affected = cur.rowcount
            if affected > 0:
                logger.warning(f"Cleaned up {affected} stuck jobs")

            conn.commit()

        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            conn.rollback()
        finally:
            cur.close()
            conn.close()

    def run_sync_loop(self):
        """Run continuous sync loop"""
        logger.info("Starting job tracker sync loop...")
        while True:
            try:
                self.sync_comfyui_jobs()
                self.cleanup_stuck_jobs()
                time.sleep(10)  # Sync every 10 seconds
            except KeyboardInterrupt:
                logger.info("Sync loop stopped")
                break
            except Exception as e:
                logger.error(f"Sync loop error: {e}")
                time.sleep(30)

if __name__ == "__main__":
    tracker = JobTracker()
    tracker.run_sync_loop()
