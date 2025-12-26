"""
character_studio/character_sheets.py
Character sheet generation for animation production
Phase 2: Character Consistency & Expressions
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from .client import ComfyUIClient
from .schemas import CharacterGenerateRequest

logger = logging.getLogger(__name__)

# Configuration
CHARACTER_ASSETS_DIR = Path("/mnt/1TB-storage/character_assets")
POSE_LIBRARY_DIR = Path("/mnt/1TB-storage/pose_library")
POSE_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)


class CharacterSheetGenerator:
    """Generate animation-ready character sheets"""
    
    # Standard turnaround angles
    TURNAROUND_ANGLES = [
        "front",
        "front_3quarter",
        "side",
        "back_3quarter",
        "back",
        "back_3quarter_alt",
        "side_alt",
        "front_3quarter_alt"
    ]
    
    # Standard expressions for animation
    STANDARD_EXPRESSIONS = [
        "neutral",
        "happy",
        "sad",
        "angry",
        "surprised",
        "fearful",
        "disgusted",
        "excited",
        "thinking",
        "smirking"
    ]
    
    # Common animation poses
    STANDARD_POSES = [
        "standing_idle",
        "sitting_chair",
        "walking_forward",
        "running",
        "reaching_up",
        "pointing",
        "arms_crossed",
        "hands_on_hips"
    ]
    
    def __init__(self):
        self.client = ComfyUIClient()
    
    async def generate_turnaround(
        self,
        character_id: int,
        base_request: CharacterGenerateRequest,
        db: Session,
        angles: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Generate 8-view character turnaround sheet
        
        Args:
            character_id: ID of base character generation
            base_request: Base character generation parameters
            db: Database session
            angles: Specific angles to generate (default: all 8 angles)
        
        Returns:
            List of generated turnaround images with metadata
        """
        angles = angles or self.TURNAROUND_ANGLES
        results = []
        
        logger.info(f"Generating turnaround sheet for character {character_id} with {len(angles)} angles")
        
        for angle in angles:
            # Modify prompt for specific angle
            angle_prompt = self._create_angle_prompt(base_request.prompt, angle)
            
            # Generate image with angle-specific prompt
            turnaround_request = CharacterGenerateRequest(
                character_name=base_request.character_name,
                project=base_request.project,
                scene=f"turnaround_{angle}",
                action="reference_pose",
                prompt=angle_prompt,
                negative_prompt=base_request.negative_prompt,
                checkpoint=base_request.checkpoint,
                loras=base_request.loras,
                seed=base_request.seed + angles.index(angle) if base_request.seed > 0 else -1,
                width=base_request.width,
                height=base_request.height,
                steps=base_request.steps,
                cfg_scale=base_request.cfg_scale,
                sampler=base_request.sampler,
                scheduler=base_request.scheduler
            )
            
            # Generate using existing character generation pipeline
            from .service import CharacterGenerationService
            service = CharacterGenerationService()
            
            try:
                result = await service.generate_character(turnaround_request, db)
                
                # Record in turnarounds table
                from models import CharacterTurnaround
                turnaround_record = CharacterTurnaround(
                    character_id=character_id,
                    angle=angle,
                    image_path=result.output_path,
                    comfyui_prompt_id=result.comfyui_prompt_id,
                    seed=result.seed
                )
                db.add(turnaround_record)
                db.commit()
                
                results.append({
                    "angle": angle,
                    "image_path": result.output_path,
                    "seed": result.seed,
                    "job_id": result.job_id
                })
                
                logger.info(f"Generated turnaround angle: {angle}")
                
            except Exception as e:
                logger.error(f"Failed to generate angle {angle}: {e}")
                results.append({
                    "angle": angle,
                    "error": str(e)
                })
        
        return results
    
    async def generate_expressions(
        self,
        character_id: int,
        base_request: CharacterGenerateRequest,
        db: Session,
        expressions: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Generate facial expression set for animation
        
        Args:
            character_id: ID of base character generation
            base_request: Base character generation parameters
            db: Database session
            expressions: Specific expressions to generate
        
        Returns:
            List of generated expression images with metadata
        """
        expressions = expressions or self.STANDARD_EXPRESSIONS[:5]  # Default to 5 basic
        results = []
        
        logger.info(f"Generating expression sheet for character {character_id} with {len(expressions)} expressions")
        
        for expression in expressions:
            # Modify prompt for specific expression
            expression_prompt = self._create_expression_prompt(base_request.prompt, expression)
            
            # Generate image with expression-specific prompt
            expression_request = CharacterGenerateRequest(
                character_name=base_request.character_name,
                project=base_request.project,
                scene=f"expression_{expression}",
                action="facial_reference",
                prompt=expression_prompt,
                negative_prompt=base_request.negative_prompt,
                checkpoint=base_request.checkpoint,
                loras=base_request.loras,
                seed=base_request.seed + 100 + expressions.index(expression) if base_request.seed > 0 else -1,
                width=512,  # Smaller for expression close-ups
                height=768,
                steps=base_request.steps,
                cfg_scale=base_request.cfg_scale,
                sampler=base_request.sampler,
                scheduler=base_request.scheduler
            )
            
            # Generate using existing character generation pipeline
            from .service import CharacterGenerationService
            service = CharacterGenerationService()
            
            try:
                result = await service.generate_character(expression_request, db)
                
                # Record in expressions table
                from models import CharacterExpression
                expression_record = CharacterExpression(
                    character_id=character_id,
                    expression=expression,
                    image_path=result.output_path,
                    comfyui_prompt_id=result.comfyui_prompt_id,
                    seed=result.seed
                )
                db.add(expression_record)
                db.commit()
                
                results.append({
                    "expression": expression,
                    "image_path": result.output_path,
                    "seed": result.seed,
                    "job_id": result.job_id
                })
                
                logger.info(f"Generated expression: {expression}")
                
            except Exception as e:
                logger.error(f"Failed to generate expression {expression}: {e}")
                results.append({
                    "expression": expression,
                    "error": str(e)
                })
        
        return results
    
    async def generate_pose_sheet(
        self,
        character_id: int,
        base_request: CharacterGenerateRequest,
        db: Session,
        poses: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Generate character in different poses for animation reference
        
        Args:
            character_id: ID of base character generation
            base_request: Base character generation parameters
            db: Database session
            poses: Specific poses to generate
        
        Returns:
            List of generated pose images with metadata
        """
        poses = poses or self.STANDARD_POSES[:4]  # Default to 4 basic poses
        results = []
        
        logger.info(f"Generating pose sheet for character {character_id} with {len(poses)} poses")
        
        for pose in poses:
            # Modify prompt for specific pose
            pose_prompt = self._create_pose_prompt(base_request.prompt, pose)
            
            # Generate image with pose-specific prompt
            pose_request = CharacterGenerateRequest(
                character_name=base_request.character_name,
                project=base_request.project,
                scene=f"pose_{pose}",
                action="pose_reference",
                prompt=pose_prompt,
                negative_prompt=base_request.negative_prompt,
                checkpoint=base_request.checkpoint,
                loras=base_request.loras,
                seed=base_request.seed + 200 + poses.index(pose) if base_request.seed > 0 else -1,
                width=base_request.width,
                height=base_request.height,
                steps=base_request.steps,
                cfg_scale=base_request.cfg_scale,
                sampler=base_request.sampler,
                scheduler=base_request.scheduler
            )
            
            # Generate using existing character generation pipeline
            from .service import CharacterGenerationService
            service = CharacterGenerationService()
            
            try:
                result = await service.generate_character(pose_request, db)
                
                results.append({
                    "pose": pose,
                    "image_path": result.output_path,
                    "seed": result.seed,
                    "job_id": result.job_id
                })
                
                logger.info(f"Generated pose: {pose}")
                
            except Exception as e:
                logger.error(f"Failed to generate pose {pose}: {e}")
                results.append({
                    "pose": pose,
                    "error": str(e)
                })
        
        return results
    
    def _create_angle_prompt(self, base_prompt: str, angle: str) -> str:
        """Modify prompt for specific camera angle"""
        angle_modifiers = {
            "front": "facing camera directly, front view, straight on",
            "front_3quarter": "3/4 front view, slightly turned, angled view",
            "side": "side profile, 90 degree angle, profile view",
            "back_3quarter": "3/4 back view, turned away, rear angle",
            "back": "back view, facing away from camera, rear view",
            "back_3quarter_alt": "3/4 back view from other side",
            "side_alt": "side profile from other side",
            "front_3quarter_alt": "3/4 front view from other side"
        }
        
        modifier = angle_modifiers.get(angle, "front view")
        return f"{base_prompt}, {modifier}, character turnaround sheet, reference pose, T-pose stance, neutral expression, white background, character design sheet"
    
    def _create_expression_prompt(self, base_prompt: str, expression: str) -> str:
        """Modify prompt for specific facial expression"""
        expression_modifiers = {
            "neutral": "neutral expression, calm face, resting face",
            "happy": "happy smiling expression, joyful face, cheerful smile",
            "sad": "sad expression, downcast eyes, melancholic face",
            "angry": "angry expression, furrowed brows, intense glare",
            "surprised": "surprised expression, wide eyes, open mouth, shocked face",
            "fearful": "fearful expression, worried eyes, frightened face",
            "disgusted": "disgusted expression, wrinkled nose, distaste",
            "excited": "excited expression, bright eyes, eager smile",
            "thinking": "thinking expression, contemplative look, hand on chin",
            "smirking": "smirking expression, sly smile, confident smirk"
        }
        
        modifier = expression_modifiers.get(expression, "neutral expression")
        return f"{base_prompt}, close-up portrait, {modifier}, detailed facial features, expressive face, front view"
    
    def _create_pose_prompt(self, base_prompt: str, pose: str) -> str:
        """Modify prompt for specific body pose"""
        pose_modifiers = {
            "standing_idle": "standing idle pose, relaxed stance, arms at sides",
            "sitting_chair": "sitting on chair, seated pose, relaxed posture",
            "walking_forward": "walking forward, mid-stride, natural gait",
            "running": "running pose, dynamic motion, athletic stance",
            "reaching_up": "reaching upward, arm extended up, stretching",
            "pointing": "pointing gesture, arm extended, finger pointing",
            "arms_crossed": "arms crossed over chest, confident stance",
            "hands_on_hips": "hands on hips, assertive pose, power stance"
        }
        
        modifier = pose_modifiers.get(pose, "standing pose")
        return f"{base_prompt}, full body shot, {modifier}, whole body visible, character reference"
