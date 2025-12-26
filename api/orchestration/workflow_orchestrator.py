"""
Main Workflow Orchestrator - The Conductor of the Animation Orchestra
Coordinates all generation components and manages the production pipeline
"""

import asyncio
import json
import uuid
import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
import traceback

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update

# Import our orchestration components
from .comfyui_api_client import ComfyUIAPIClient, DynamicWorkflowBuilder
from .condition_compiler import ConditionCompiler, SceneRequest, GenerationCondition, ConditionType
from .unified_embedding_pipeline import UnifiedEmbeddingPipeline, EmbeddingType

# Import database models
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.database import GenerationJob, ProjectCharacter, AnimationProject

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Job lifecycle states"""
    QUEUED = "queued"
    PREPARING = "preparing"
    COMPILING = "compiling"
    EXECUTING = "executing"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPriority(Enum):
    """Job priority levels"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass
class JobContext:
    """Complete context for a generation job"""
    job_id: str
    project_id: Optional[str]
    character_id: Optional[str]
    scene_request: SceneRequest
    workflow: Optional[Dict[str, Any]] = None
    status: JobStatus = JobStatus.QUEUED
    priority: JobPriority = JobPriority.NORMAL
    progress: float = 0.0
    current_step: str = "Initializing"
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class WorkflowOrchestrator:
    """
    The main orchestrator that conducts the entire animation generation pipeline.
    Acts as the central coordinator between all subsystems.
    """

    def __init__(self,
                 postgres_config: Dict[str, Any],
                 redis_url: str = "redis://localhost:6379",
                 comfyui_url: str = "http://127.0.0.1:8188",
                 qdrant_url: str = "http://localhost:6333"):
        
        self.postgres_config = postgres_config
        self.redis_url = redis_url
        self.comfyui_url = comfyui_url
        self.qdrant_url = qdrant_url
        
        # Initialize components
        self.comfyui_client = None
        self.condition_compiler = None
        self.embedding_pipeline = None
        self.redis_client = None
        self.db_engine = None
        self.db_session_maker = None
        
        # Job tracking
        self.active_jobs: Dict[str, JobContext] = {}
        self.job_queue: asyncio.Queue = asyncio.Queue()
        self.worker_tasks: List[asyncio.Task] = []
        
        # Performance Configuration
        self.max_concurrent_jobs = 6  # Increased for better throughput
        self.worker_count = 4  # Increased for multi-core utilization
        self.batch_size = 10  # Process multiple jobs in batches
        self.connection_pool_size = 20  # DB connection pool
        self.redis_pool_size = 10  # Redis connection pool
        self.cache_ttl = 300  # 5 minutes cache for embeddings
        self.progress_update_interval = 0.5  # Faster updates

        # Performance metrics
        self.metrics = {
            'jobs_processed': 0,
            'avg_processing_time': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'active_connections': 0
        }
        
    async def initialize(self):
        """Initialize all components and connections"""
        logger.info("Initializing Workflow Orchestrator...")
        
        # Initialize database
        await self._init_database()
        
        # Initialize Redis
        self.redis_client = await redis.from_url(self.redis_url)
        
        # Initialize orchestration components
        self.comfyui_client = ComfyUIAPIClient(self.comfyui_url)
        self.embedding_pipeline = UnifiedEmbeddingPipeline(
            postgres_config=self.postgres_config,
            qdrant_url=self.qdrant_url
        )
        self.condition_compiler = ConditionCompiler(
            vector_db_client=self.embedding_pipeline.qdrant_client,
            asset_manager=None  # Will implement asset manager later
        )
        
        # Start worker tasks
        for i in range(self.worker_count):
            task = asyncio.create_task(self._job_worker(f"worker-{i}"))
            self.worker_tasks.append(task)
        
        logger.info("Workflow Orchestrator initialized successfully")

    async def _init_database(self):
        """Initialize database connection"""
        # Create async engine
        db_url = f"postgresql+asyncpg://{self.postgres_config['user']}:{self.postgres_config['password']}@" \
                 f"{self.postgres_config['host']}:{self.postgres_config.get('port', 5432)}/{self.postgres_config['database']}"
        
        self.db_engine = create_async_engine(db_url, echo=False)
        self.db_session_maker = sessionmaker(
            self.db_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    async def submit_generation(self,
                               scene_request: SceneRequest,
                               project_id: Optional[str] = None,
                               character_id: Optional[str] = None,
                               priority: JobPriority = JobPriority.NORMAL) -> str:
        """
        Submit a new generation job to the orchestrator.
        
        Args:
            scene_request: The scene generation request
            project_id: Optional project ID
            character_id: Optional character ID
            priority: Job priority
            
        Returns:
            Job ID for tracking
        """
        job_id = str(uuid.uuid4())
        
        # Create job context
        job_context = JobContext(
            job_id=job_id,
            project_id=project_id,
            character_id=character_id,
            scene_request=scene_request,
            priority=priority
        )
        
        # Store in active jobs
        self.active_jobs[job_id] = job_context
        
        # Create database entry
        async with self.db_session_maker() as session:
            job = GenerationJob(
                id=job_id,
                project_id=project_id,
                character_id=character_id,
                generation_type=scene_request.output_format,
                status="queued",
                parameters={
                    "scene_request": {
                        "scene_id": scene_request.scene_id,
                        "storyline_text": scene_request.storyline_text,
                        "resolution": list(scene_request.resolution),
                        "duration_seconds": scene_request.duration_seconds,
                        "fps": scene_request.fps,
                        "style_preset": scene_request.style_preset
                    }
                },
                created_at=job_context.created_at
            )
            session.add(job)
            await session.commit()
        
        # Add to queue based on priority
        await self.job_queue.put((priority.value, job_id))
        
        # Publish to Redis for real-time updates
        await self._publish_job_update(job_id, {
            "status": "queued",
            "job_id": job_id,
            "message": "Job queued for processing"
        })
        
        logger.info(f"Job {job_id} submitted with priority {priority.name}")
        return job_id

    async def _job_worker(self, worker_name: str):
        """Worker task that processes jobs from the queue"""
        logger.info(f"{worker_name} started")
        
        while True:
            try:
                # Get job from queue (priority-based)
                priority, job_id = await self.job_queue.get()
                
                if job_id not in self.active_jobs:
                    logger.warning(f"Job {job_id} not found in active jobs")
                    continue
                
                job_context = self.active_jobs[job_id]
                
                # Check if we can process (respect concurrent job limit)
                active_count = sum(
                    1 for j in self.active_jobs.values()
                    if j.status in [JobStatus.EXECUTING, JobStatus.PROCESSING]
                )
                
                if active_count >= self.max_concurrent_jobs:
                    # Re-queue the job
                    await self.job_queue.put((priority, job_id))
                    await asyncio.sleep(5)  # Wait before trying again
                    continue
                
                # Process the job
                logger.info(f"{worker_name} processing job {job_id}")
                await self._process_job(job_context)
                
            except Exception as e:
                logger.error(f"{worker_name} error: {e}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(1)

    async def _process_job(self, job_context: JobContext):
        """Process a single job through the entire pipeline"""
        job_id = job_context.job_id
        
        try:
            # Update status to preparing
            await self._update_job_status(job_context, JobStatus.PREPARING, "Preparing generation")
            
            # Step 1: Validate conditions
            errors = self.condition_compiler.validate_conditions(job_context.scene_request.conditions)
            if errors:
                raise ValueError(f"Invalid conditions: {'; '.join(errors)}")
            
            # Step 2: Process embeddings for any reference images
            await self._update_job_status(job_context, JobStatus.PREPARING, "Processing embeddings")
            await self._process_embeddings(job_context)
            
            # Step 3: Compile workflow
            await self._update_job_status(job_context, JobStatus.COMPILING, "Compiling workflow")
            workflow = self.condition_compiler.compile_scene(job_context.scene_request)
            job_context.workflow = workflow
            
            # Step 4: Execute workflow on ComfyUI
            await self._update_job_status(job_context, JobStatus.EXECUTING, "Executing on ComfyUI")
            
            async with self.comfyui_client:
                prompt_id = await self.comfyui_client.execute_workflow(workflow)
                
                # Monitor progress
                await self._monitor_comfyui_execution(job_context, prompt_id)
                
                # Wait for completion
                result = await self.comfyui_client.wait_for_completion(prompt_id, timeout=300)
                job_context.result = result
            
            # Step 5: Post-process results
            await self._update_job_status(job_context, JobStatus.PROCESSING, "Post-processing results")
            await self._post_process_results(job_context)
            
            # Mark as completed
            await self._update_job_status(job_context, JobStatus.COMPLETED, "Generation completed")
            
            logger.info(f"Job {job_id} completed successfully")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Job {job_id} failed: {error_msg}")
            logger.error(traceback.format_exc())
            
            job_context.error = error_msg
            await self._update_job_status(job_context, JobStatus.FAILED, f"Failed: {error_msg}")
        
        finally:
            # Clean up job after delay
            asyncio.create_task(self._cleanup_job(job_id))

    async def _process_embeddings(self, job_context: JobContext):
        """Process and store embeddings for reference materials"""
        scene_request = job_context.scene_request
        
        for condition in scene_request.conditions:
            if condition.type == ConditionType.CHARACTER_IDENTITY:
                if "reference_image" in condition.data:
                    # Generate and store character embedding
                    embedding_result = self.embedding_pipeline.generate_embedding(
                        source=condition.data["reference_image"],
                        embedding_type=EmbeddingType.CHARACTER,
                        metadata={
                            "character_id": job_context.character_id,
                            "job_id": job_context.job_id
                        }
                    )
                    condition.data["embedding_id"] = embedding_result.embedding_id
                    
            elif condition.type == ConditionType.STYLE_REFERENCE:
                if "style_image" in condition.data:
                    # Generate style embedding
                    embedding_result = self.embedding_pipeline.generate_embedding(
                        source=condition.data["style_image"],
                        embedding_type=EmbeddingType.STYLE,
                        metadata={
                            "job_id": job_context.job_id
                        }
                    )
                    condition.data["embedding_id"] = embedding_result.embedding_id

    async def _monitor_comfyui_execution(self, job_context: JobContext, prompt_id: str):
        """Monitor ComfyUI execution and update progress"""
        # This would connect to ComfyUI WebSocket for real-time updates
        # For now, simulate progress updates
        
        for progress in range(0, 101, 10):
            job_context.progress = progress
            
            await self._publish_job_update(job_context.job_id, {
                "status": "executing",
                "progress": progress,
                "message": f"Generating... {progress}%"
            })
            
            await asyncio.sleep(1)  # Simulate processing time

    async def _post_process_results(self, job_context: JobContext):
        """Post-process generation results"""
        if not job_context.result:
            return
        
        # Extract output files
        outputs = job_context.result.get("outputs", {})
        
        # Store file paths in database
        async with self.db_session_maker() as session:
            result = await session.execute(
                update(GenerationJob)
                .where(GenerationJob.id == job_context.job_id)
                .values(
                    result=outputs,
                    completed_at=datetime.now()
                )
            )
            await session.commit()
        
        # If this is for a character, update character record
        if job_context.character_id:
            await self._update_character_generation(job_context)

    async def _update_character_generation(self, job_context: JobContext):
        """Update character with latest generation results"""
        async with self.db_session_maker() as session:
            character = await session.get(ProjectCharacter, job_context.character_id)
            if character:
                # Update with latest generation
                if job_context.result and "outputs" in job_context.result:
                    outputs = job_context.result["outputs"]
                    if "images" in outputs:
                        character.last_generated_image = outputs["images"][0]
                    if "videos" in outputs:
                        character.last_generated_video = outputs["videos"][0]
                    
                    character.generation_count = (character.generation_count or 0) + 1
                    character.updated_at = datetime.now()
                    
                    await session.commit()

    async def _update_job_status(self, job_context: JobContext, status: JobStatus, message: str):
        """Update job status in memory, database, and publish update"""
        job_context.status = status
        job_context.current_step = message
        
        if status == JobStatus.EXECUTING and not job_context.started_at:
            job_context.started_at = datetime.now()
        elif status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            job_context.completed_at = datetime.now()
        
        # Update database
        async with self.db_session_maker() as session:
            result = await session.execute(
                update(GenerationJob)
                .where(GenerationJob.id == job_context.job_id)
                .values(
                    status=status.value,
                    progress=job_context.progress,
                    error_message=job_context.error
                )
            )
            await session.commit()
        
        # Publish real-time update
        await self._publish_job_update(job_context.job_id, {
            "status": status.value,
            "progress": job_context.progress,
            "message": message,
            "error": job_context.error
        })

    async def _publish_job_update(self, job_id: str, update: Dict[str, Any]):
        """Publish job update to Redis for WebSocket distribution"""
        channel = f"job:{job_id}"
        update["timestamp"] = datetime.now().isoformat()
        update["job_id"] = job_id
        
        await self.redis_client.publish(channel, json.dumps(update))

    async def _cleanup_job(self, job_id: str, delay: int = 300):
        """Clean up job from memory after delay"""
        await asyncio.sleep(delay)
        if job_id in self.active_jobs:
            del self.active_jobs[job_id]
            logger.info(f"Cleaned up job {job_id} from memory")

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of a job"""
        if job_id in self.active_jobs:
            job_context = self.active_jobs[job_id]
            return {
                "job_id": job_id,
                "status": job_context.status.value,
                "progress": job_context.progress,
                "current_step": job_context.current_step,
                "created_at": job_context.created_at.isoformat(),
                "started_at": job_context.started_at.isoformat() if job_context.started_at else None,
                "completed_at": job_context.completed_at.isoformat() if job_context.completed_at else None,
                "error": job_context.error,
                "result": job_context.result
            }
        
        # Check database for completed jobs
        async with self.db_session_maker() as session:
            result = await session.execute(
                select(GenerationJob).where(GenerationJob.id == job_id)
            )
            job = result.scalar_one_or_none()
            
            if job:
                return {
                    "job_id": job.id,
                    "status": job.status,
                    "progress": job.progress or 0,
                    "created_at": job.created_at.isoformat(),
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                    "error": job.error_message,
                    "result": job.result
                }
        
        return None

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a job"""
        if job_id in self.active_jobs:
            job_context = self.active_jobs[job_id]
            
            if job_context.status in [JobStatus.QUEUED, JobStatus.PREPARING]:
                await self._update_job_status(job_context, JobStatus.CANCELLED, "Cancelled by user")
                return True
            elif job_context.status == JobStatus.EXECUTING:
                # Interrupt ComfyUI execution
                async with self.comfyui_client:
                    await self.comfyui_client.interrupt_execution()
                await self._update_job_status(job_context, JobStatus.CANCELLED, "Cancelled during execution")
                return True
        
        return False

    async def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue and processing status"""
        queued_jobs = [j for j in self.active_jobs.values() if j.status == JobStatus.QUEUED]
        processing_jobs = [j for j in self.active_jobs.values() 
                          if j.status in [JobStatus.EXECUTING, JobStatus.PROCESSING]]
        
        return {
            "queue_size": len(queued_jobs),
            "processing_count": len(processing_jobs),
            "max_concurrent": self.max_concurrent_jobs,
            "worker_count": self.worker_count,
            "queued_jobs": [
                {
                    "job_id": j.job_id,
                    "priority": j.priority.name,
                    "created_at": j.created_at.isoformat()
                }
                for j in sorted(queued_jobs, key=lambda x: (x.priority.value, x.created_at), reverse=True)
            ],
            "processing_jobs": [
                {
                    "job_id": j.job_id,
                    "status": j.status.value,
                    "progress": j.progress,
                    "current_step": j.current_step
                }
                for j in processing_jobs
            ]
        }

    async def shutdown(self):
        """Graceful shutdown of orchestrator"""
        logger.info("Shutting down Workflow Orchestrator...")
        
        # Cancel worker tasks
        for task in self.worker_tasks:
            task.cancel()
        
        # Wait for workers to finish
        await asyncio.gather(*self.worker_tasks, return_exceptions=True)
        
        # Close connections
        if self.redis_client:
            await self.redis_client.close()
        
        if self.embedding_pipeline:
            self.embedding_pipeline.close()
        
        if self.db_engine:
            await self.db_engine.dispose()
        
        logger.info("Workflow Orchestrator shutdown complete")