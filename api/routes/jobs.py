"""Job management routes"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from pathlib import Path
import logging
import redis

from job_tracker_fixed import job_tracker
from auth_middleware import optional_auth

logger = logging.getLogger(__name__)
router = APIRouter()

# Redis client for queue stats
redis_client = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)


@router.get("/api/anime/jobs")
async def list_jobs(
    status: str = None,
    limit: int = 100,
    user=Depends(optional_auth)
):
    """List all jobs with optional status filter"""
    try:
        if status:
            jobs = job_tracker.list_jobs(status=status)
        else:
            # Get all jobs
            all_jobs = []
            for s in ["pending", "processing", "completed", "failed"]:
                all_jobs.extend(job_tracker.list_jobs(status=s))
            jobs = all_jobs[:limit]

        return {
            "jobs": jobs,
            "count": len(jobs),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/anime/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get detailed job status"""
    try:
        job = job_tracker.get_job(job_id)

        if not job:
            raise HTTPException(
                status_code=404,
                detail=f"Job {job_id} not found"
            )

        # Check for output files
        output_path = Path(f"/mnt/1TB-storage/ComfyUI/output/{job_id}_00001.png")
        has_output = output_path.exists()

        return {
            "job_id": job_id,
            "status": job["status"],
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
            "data": job.get("data"),
            "progress": job.get("progress", 0),
            "has_output": has_output,
            "output_path": str(output_path) if has_output else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job {job_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get job status: {str(e)}"
        )


@router.get("/api/anime/generation/{job_id}/status")
async def get_generation_status(job_id: str):
    """Get generation job status with progress"""
    return await get_job_status(job_id)


@router.delete("/api/anime/jobs/{job_id}")
async def cancel_job(
    job_id: str,
    user=Depends(optional_auth)
):
    """Cancel a job"""
    try:
        job = job_tracker.get_job(job_id)

        if not job:
            raise HTTPException(
                status_code=404,
                detail=f"Job {job_id} not found"
            )

        if job["status"] in ["completed", "failed"]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel job in {job['status']} state"
            )

        job_tracker.update_job_status(job_id, "cancelled")

        return {
            "job_id": job_id,
            "status": "cancelled",
            "message": "Job cancelled successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel job {job_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel job: {str(e)}"
        )


@router.get("/api/anime/queue")
async def get_queue_status():
    """Get current queue status with detailed metrics"""
    try:
        # Get queue lengths
        pending = redis_client.llen("anime:job:queue")
        processing = redis_client.llen("anime:job:processing")

        # Get recent completed/failed counts
        completed_keys = redis_client.keys("anime:job:*")
        completed_count = 0
        failed_count = 0

        for key in completed_keys[:100]:  # Check last 100 jobs
            if key.startswith("anime:job:") and len(key.split(":")) == 3:
                job_data = redis_client.hgetall(key)
                if job_data.get("status") == "completed":
                    completed_count += 1
                elif job_data.get("status") == "failed":
                    failed_count += 1

        # Check worker status
        worker_active = False
        try:
            import psutil
            for proc in psutil.process_iter(['name', 'cmdline']):
                if 'worker.py' in str(proc.info['cmdline']):
                    worker_active = True
                    break
        except:
            pass

        return {
            "queue": {
                "pending": pending,
                "processing": processing,
                "completed": completed_count,
                "failed": failed_count,
                "total": pending + processing
            },
            "workers": {
                "active": 1 if worker_active else 0,
                "status": "running" if worker_active else "stopped"
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get queue status: {e}")
        return {
            "queue": {"pending": 0, "processing": 0, "total": 0},
            "workers": {"active": 0, "status": "error"},
            "error": str(e)
        }