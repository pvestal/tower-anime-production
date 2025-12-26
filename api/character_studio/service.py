"""
character_studio/service.py
Business logic for character generation
"""

import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from .client import ComfyUIClient
from .schemas import CharacterGenerateRequest, CharacterGenerateResponse

logger = logging.getLogger(__name__)

# Configuration
COMFYUI_OUTPUT_DIR = Path("/mnt/1TB-storage/ComfyUI/output")
CHARACTER_ASSETS_DIR = Path("/mnt/1TB-storage/character_assets")


class CharacterGenerationService:
    """Service layer for character generation"""

    def __init__(self):
        self.client = ComfyUIClient()

    async def generate_character(
        self,
        request: CharacterGenerateRequest,
        db: Session
    ) -> CharacterGenerateResponse:
        """
        Main orchestration: Generate character and persist metadata

        Returns:
            CharacterGenerateResponse with job details
        """
        job_id = str(uuid.uuid4())
        created_at = datetime.now()

        logger.info(f"Starting character generation {job_id}: {request.character_name or 'unnamed'}")

        try:
            # Build workflow
            filename_prefix = f"char_{job_id[:8]}"

            # Convert LoRA configs to dicts
            loras_list = None
            if request.loras:
                loras_list = [lora.dict() for lora in request.loras]

            workflow = await self.client.build_character_workflow(
                prompt=request.prompt,
                negative_prompt=request.negative_prompt,
                checkpoint=request.checkpoint,
                loras=loras_list,
                sampler=request.sampler,
                scheduler=request.scheduler,
                width=request.width,
                height=request.height,
                steps=request.steps,
                cfg_scale=request.cfg_scale,
                seed=request.seed,
                use_controlnet=request.use_controlnet,
                controlnet_model=request.controlnet_model if request.use_controlnet else None,
                pose_reference=request.pose_reference if request.use_controlnet else None,
                filename_prefix=filename_prefix
            )

            # Extract actual seed used
            ksampler_node = workflow.get("4", {})
            actual_seed = ksampler_node.get("inputs", {}).get("seed", request.seed)

            # Submit to ComfyUI
            prompt_id = await self.client.submit_workflow(workflow)

            # Wait for completion
            output_filename = await self.client.poll_until_complete(prompt_id, timeout=300)

            if not output_filename:
                raise Exception("Generation timeout or failed")

            # Move file to character_assets
            final_path = self._organize_output_file(
                output_filename,
                request.character_name,
                request.project,
                request.scene,
                request.action,
                actual_seed,
                job_id
            )

            # Save to database
            from models import GenerationJob  # Fixed import
            db_record = CharacterGeneration(
                job_id=job_id,
                character_name=request.character_name,
                project=request.project,
                prompt=request.prompt,
                negative_prompt=request.negative_prompt,
                checkpoint=request.checkpoint,
                width=request.width,
                height=request.height,
                steps=request.steps,
                cfg_scale=request.cfg_scale,
                seed=actual_seed,
                scene=request.scene,
                action=request.action,
                sampler_name=request.sampler,
                scheduler=request.scheduler,
                use_controlnet=request.use_controlnet,
                controlnet_model=request.controlnet_model if request.use_controlnet else None,
                pose_reference=request.pose_reference if request.use_controlnet else None,
                output_path=str(final_path),
                comfyui_prompt_id=prompt_id,
                status="completed",
                created_at=created_at,
                completed_at=datetime.now()
            )

            db.add(db_record)
            db.commit()
            db.refresh(db_record)

            logger.info(f"Character generation completed: {job_id}")

            return CharacterGenerateResponse(
                job_id=job_id,
                character_name=request.character_name,
                project=request.project,
                status="completed",
                output_path=str(final_path),
                comfyui_prompt_id=prompt_id,
                seed=actual_seed,
                created_at=created_at.isoformat(),
                completed_at=datetime.now().isoformat()
            )

        except Exception as e:
            logger.error(f"Character generation failed for {job_id}: {e}", exc_info=True)

            # Save failure to database
            try:
                from models import GenerationJob  # Fixed import
                db_record = CharacterGeneration(
                    job_id=job_id,
                    character_name=request.character_name,
                    project=request.project,
                    prompt=request.prompt,
                    negative_prompt=request.negative_prompt,
                    checkpoint=request.checkpoint,
                    width=request.width,
                    height=request.height,
                    steps=request.steps,
                    cfg_scale=request.cfg_scale,
                    seed=request.seed,
                    scene=request.scene,
                    action=request.action,
                    sampler_name=request.sampler,
                    scheduler=request.scheduler,
                    use_controlnet=request.use_controlnet,
                    status="failed",
                    error_message=str(e),
                    created_at=created_at
                )
                db.add(db_record)
                db.commit()
            except Exception as db_error:
                logger.error(f"Failed to save error to database: {db_error}")

            raise Exception(f"Character generation failed: {str(e)}")

    def _organize_output_file(
        self,
        comfyui_filename: str,
        character_name: Optional[str],
        project: str,
        scene: Optional[str],
        action: Optional[str],
        seed: int,
        job_id: str
    ) -> Path:
        """
        Move file from ComfyUI output to organized character_assets directory
        Filename format: project_character_scene_action_date_seed.png

        Returns final path
        """
        source_path = COMFYUI_OUTPUT_DIR / comfyui_filename

        if not source_path.exists():
            raise FileNotFoundError(f"ComfyUI output not found: {source_path}")

        # Create project directory
        project_dir = CHARACTER_ASSETS_DIR / project
        project_dir.mkdir(parents=True, exist_ok=True)

        # Generate organized filename with metadata
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        extension = source_path.suffix
        
        # Build filename parts: project_character_scene_action_date_seed
        parts = []
        parts.append(self._slugify(project) if project else "default")
        parts.append(self._slugify(character_name) if character_name else "character")
        if scene:
            parts.append(self._slugify(scene))
        if action:
            parts.append(self._slugify(action))
        parts.append(timestamp)
        parts.append(f"seed{seed}")
        
        final_filename = "_".join(parts) + extension

        dest_path = project_dir / final_filename

        # Move file
        shutil.move(str(source_path), str(dest_path))
        logger.info(f"Moved {source_path} → {dest_path}")

        return dest_path

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert text to filesystem-safe slug"""
        return "".join(
            c if c.isalnum() or c in ('-', '_') else '_'
            for c in text.lower()
        )

    async def get_character_by_id(self, character_id: int, db: Session):
        """Get character generation record by ID"""
        from models import CharacterGeneration
        return db.query(CharacterGeneration).filter(
            CharacterGeneration.id == character_id
        ).first()

    async def list_characters(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 20,
        project: Optional[str] = None
    ) -> Tuple[list, int]:
        """
        List character generations with pagination

        Returns (characters, total_count)
        """
        from models import CharacterGeneration

        query = db.query(CharacterGeneration)

        if project:
            query = query.filter(CharacterGeneration.project == project)

        total = query.count()

        characters = query.order_by(
            CharacterGeneration.created_at.desc()
        ).offset(skip).limit(limit).all()

        return characters, total
