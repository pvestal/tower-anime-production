"""
character_studio/router_animation.py
Phase 3: Animation API Endpoints - Full Implementation
Integrates AnimationGenerator for actual frame generation, FFmpeg compilation, and lip sync
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, File, UploadFile
from sqlalchemy.orm import Session
from typing import List, Optional
from pathlib import Path
import json
from datetime import datetime
import shutil
import asyncio

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_db
# from models import CharacterGeneration, AnimationSequence  # Models not available yet

# Import our complete animation system
from character_studio.animation_generator import AnimationGenerator
from character_studio.schemas_animation import (
    AnimationRequest,
    AnimationResponse,
    AnimationType,
    LipSyncRequest,
    LipSyncResponse,
    PoseSequenceRequest,
    PoseSequenceResponse,
    AnimationTemplateInfo
)

router = APIRouter(prefix="/api/anime/animation", tags=["animation"])

# Initialize animation generator
animation_generator = AnimationGenerator()


async def generate_animation_background(
    animation_id: int,
    character_image_path: str,
    animation_type: str,
    pose_sequence: Optional[List[str]],
    fps: int,
    resolution: str,
    loop: bool,
    seed: int,
    db_uri: str
):
    """
    Background task for animation generation
    Runs frame generation and video compilation asynchronously
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    # Create new DB session for background task
    engine = create_engine(db_uri)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        animation = db.query(AnimationSequence).filter(
            AnimationSequence.id == animation_id
        ).first()
        
        if not animation:
            return
        
        # Update status to processing
        animation.status = "processing"
        animation.metadata = animation.metadata or {}
        animation.metadata["started_at"] = datetime.now().isoformat()
        db.commit()
        
        # Generate animation frames
        frames_result = await animation_generator.generate_animation_frames(
            character_image_path=character_image_path,
            animation_type=animation_type,
            pose_sequence=pose_sequence,
            fps=fps,
            seed=seed
        )
        
        # Update with frame paths
        animation.frame_paths = frames_result["frame_paths"]
        animation.frame_count = len(frames_result["frame_paths"])
        animation.metadata["frames_generated_at"] = datetime.now().isoformat()
        db.commit()
        
        # Compile to video
        video_result = await animation_generator.compile_to_video(
            frame_paths=frames_result["frame_paths"],
            output_filename=f"animation_{animation_id}_{animation_type}",
            fps=fps,
            resolution=resolution,
            loop=loop
        )
        
        # Update with video path
        animation.video_path = video_result["video_path"]
        animation.status = "completed"
        animation.metadata["completed_at"] = datetime.now().isoformat()
        animation.metadata["video_metadata"] = video_result["metadata"]
        animation.updated_at = datetime.now()
        db.commit()
        
    except Exception as e:
        # Update status to failed
        if animation:
            animation.status = "failed"
            animation.metadata = animation.metadata or {}
            animation.metadata["error"] = str(e)
            animation.metadata["failed_at"] = datetime.now().isoformat()
            animation.updated_at = datetime.now()
            db.commit()
        raise
    finally:
        db.close()


@router.post("/generate", response_model=AnimationResponse)
async def generate_animation(
    request: AnimationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Generate animation sequence for a character
    Phase 3: Full implementation with frame generation and video compilation
    """
    # Get character
    character = db.query(CharacterGeneration).filter(
        CharacterGeneration.id == request.character_id
    ).first()
    
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    
    # Verify character has image
    if not character.output_path or not Path(character.output_path).exists():
        raise HTTPException(
            status_code=400, 
            detail="Character image not found. Generate character turnaround first."
        )
    
    # Create animation sequence record
    animation = AnimationSequence(
        character_id=character.id,
        sequence_type=request.animation_type.value,
        frame_paths=[],
        fps=request.fps,
        frame_count=0,  # Will be updated after generation
        status="queued",
        metadata={
            "requested_at": datetime.now().isoformat(),
            "animation_params": {
                "animation_type": request.animation_type.value,
                "fps": request.fps,
                "resolution": request.resolution,
                "loop": request.loop,
                "seed": request.seed,
                "custom_poses": len(request.pose_sequence) if request.pose_sequence else 0
            }
        }
    )
    
    db.add(animation)
    db.commit()
    db.refresh(animation)
    
    # Start background generation task
    # Get DB URI from engine
    db_uri = str(db.get_bind().url)
    
    background_tasks.add_task(
        generate_animation_background,
        animation_id=animation.id,
        character_image_path=character.output_path,
        animation_type=request.animation_type.value,
        pose_sequence=request.pose_sequence,
        fps=request.fps,
        resolution=request.resolution,
        loop=request.loop,
        seed=request.seed,
        db_uri=db_uri
    )
    
    return AnimationResponse(
        animation_id=animation.id,
        character_id=character.id,
        character_name=character.character_name,
        animation_type=request.animation_type.value,
        frame_count=0,
        video_path=None,
        status="queued",
        estimated_completion="2-5 minutes",
        created_at=animation.created_at.isoformat()
    )


@router.post("/lip-sync", response_model=LipSyncResponse)
async def generate_lip_sync(
    request: LipSyncRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Generate lip-sync animation from audio file
    Phase 3: Full implementation with phoneme mapping
    """
    # Get character
    character = db.query(CharacterGeneration).filter(
        CharacterGeneration.id == request.character_id
    ).first()
    
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    
    # Verify character has image
    if not character.output_path or not Path(character.output_path).exists():
        raise HTTPException(
            status_code=400,
            detail="Character image not found. Generate character first."
        )
    
    # Verify audio file exists
    if not Path(request.audio_file_path).exists():
        raise HTTPException(
            status_code=400,
            detail=f"Audio file not found: {request.audio_file_path}"
        )
    
    # Create animation sequence for lip sync
    animation = AnimationSequence(
        character_id=character.id,
        sequence_type="lip_sync",
        frame_paths=[],
        fps=request.fps,
        status="queued",
        metadata={
            "requested_at": datetime.now().isoformat(),
            "audio_file": request.audio_file_path,
            "phonemes_provided": len(request.phonemes) if request.phonemes else 0
        }
    )
    
    db.add(animation)
    db.commit()
    db.refresh(animation)
    
    # Generate lip sync (can be done synchronously since it's fast)
    try:
        lip_sync_result = await animation_generator.create_lip_sync_animation(
            character_image_path=character.output_path,
            audio_file_path=request.audio_file_path,
            phonemes=request.phonemes,
            fps=request.fps
        )
        
        # Update animation record
        animation.status = "completed"
        animation.metadata["lip_sync_result"] = lip_sync_result
        animation.updated_at = datetime.now()
        db.commit()
        
        return LipSyncResponse(
            animation_id=animation.id,
            character_id=character.id,
            character_name=character.character_name,
            audio_duration=lip_sync_result["audio_duration"],
            total_frames=lip_sync_result["total_frames"],
            phoneme_timing=lip_sync_result["phoneme_timing"],
            status="completed",
            created_at=animation.created_at.isoformat()
        )
        
    except Exception as e:
        animation.status = "failed"
        animation.metadata["error"] = str(e)
        animation.updated_at = datetime.now()
        db.commit()
        raise HTTPException(status_code=500, detail=f"Lip sync generation failed: {str(e)}")


@router.post("/pose-sequence", response_model=PoseSequenceResponse)
async def create_pose_sequence(
    request: PoseSequenceRequest,
    db: Session = Depends(get_db)
):
    """
    Create and save a custom pose sequence
    Saves pose images to disk for reuse in animations
    """
    # Create pose sequence directory
    pose_dir = Path("/mnt/1TB-storage/poses") / request.sequence_name
    pose_dir.mkdir(parents=True, exist_ok=True)
    
    # Save pose sequence metadata
    sequence_data = {
        "sequence_name": request.sequence_name,
        "animation_type": request.animation_type,
        "poses": request.poses,
        "fps": request.fps,
        "loop": request.loop,
        "created_at": datetime.now().isoformat()
    }
    
    sequence_file = pose_dir / "sequence.json"
    with open(sequence_file, "w") as f:
        json.dump(sequence_data, f, indent=2)
    
    return PoseSequenceResponse(
        sequence_name=request.sequence_name,
        animation_type=request.animation_type,
        pose_count=len(request.poses),
        fps=request.fps,
        loop=request.loop,
        storage_path=str(pose_dir),
        status="saved",
        created_at=datetime.now().isoformat()
    )


@router.get("/sequences/{character_id}")
async def list_animation_sequences(
    character_id: int,
    db: Session = Depends(get_db)
):
    """List all animation sequences for a character"""
    sequences = db.query(AnimationSequence).filter(
        AnimationSequence.character_id == character_id
    ).order_by(AnimationSequence.created_at.desc()).all()
    
    return {
        "character_id": character_id,
        "total_sequences": len(sequences),
        "sequences": [
            {
                "id": seq.id,
                "animation_type": seq.sequence_type,
                "frame_count": seq.frame_count or 0,
                "fps": seq.fps or 24,
                "status": seq.status or "unknown",
                "video_path": seq.video_path,
                "created_at": seq.created_at.isoformat() if seq.created_at else None,
                "updated_at": seq.updated_at.isoformat() if seq.updated_at else None
            }
            for seq in sequences
        ]
    }


@router.get("/templates", response_model=List[AnimationTemplateInfo])
async def list_animation_templates():
    """List available animation templates from actual template files"""
    templates_file = Path("/opt/tower-anime-production/workflows/animation_templates/templates.json")
    
    if not templates_file.exists():
        # Fallback to hardcoded templates
        return [
            AnimationTemplateInfo(
                template_id="walk_cycle_2d",
                name="2D Walk Cycle",
                description="Basic walk cycle with OpenPose ControlNet",
                frame_count=12,
                fps=24,
                controlnet_type="openpose",
                workflow_file="walk_cycle_2d.json"
            ),
            AnimationTemplateInfo(
                template_id="idle_breathing",
                name="Idle Breathing",
                description="Subtle breathing animation with Depth ControlNet",
                frame_count=8,
                fps=12,
                controlnet_type="depth",
                workflow_file="idle_breathing.json"
            ),
            AnimationTemplateInfo(
                template_id="talking_visemes",
                name="Talking/Lip Sync",
                description="Mouth shapes for speech with Canny ControlNet",
                frame_count=6,
                fps=30,
                controlnet_type="canny",
                workflow_file="talking_visemes.json"
            )
        ]
    
    # Load templates from file
    with open(templates_file) as f:
        templates_data = json.load(f)
    
    result = []
    for template_id, template_info in templates_data.items():
        result.append(
            AnimationTemplateInfo(
                template_id=template_id,
                name=template_info.get("name", template_id.replace("_", " ").title()),
                description=template_info.get("description", ""),
                frame_count=template_info.get("frames", 12),
                fps=template_info.get("fps", 24),
                controlnet_type=template_info.get("controlnet_type", "openpose"),
                workflow_file=template_info.get("workflow_file", f"{template_id}.json")
            )
        )
    
    return result


@router.get("/status/{animation_id}")
async def get_animation_status(
    animation_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed status of an animation sequence"""
    animation = db.query(AnimationSequence).filter(
        AnimationSequence.id == animation_id
    ).first()
    
    if not animation:
        raise HTTPException(status_code=404, detail="Animation not found")
    
    # Get character info
    character = db.query(CharacterGeneration).filter(
        CharacterGeneration.id == animation.character_id
    ).first()
    
    return {
        "animation_id": animation.id,
        "character_name": character.character_name if character else None,
        "animation_type": animation.sequence_type,
        "frame_count": animation.frame_count or 0,
        "fps": animation.fps or 24,
        "status": animation.status or "unknown",
        "video_path": animation.video_path,
        "created_at": animation.created_at.isoformat() if animation.created_at else None,
        "updated_at": animation.updated_at.isoformat() if animation.updated_at else None,
        "metadata": animation.metadata
    }


@router.delete("/sequences/{animation_id}")
async def delete_animation_sequence(
    animation_id: int,
    db: Session = Depends(get_db)
):
    """Delete an animation sequence and its associated files"""
    animation = db.query(AnimationSequence).filter(
        AnimationSequence.id == animation_id
    ).first()
    
    if not animation:
        raise HTTPException(status_code=404, detail="Animation not found")
    
    # Delete video file if exists
    if animation.video_path and Path(animation.video_path).exists():
        Path(animation.video_path).unlink()
    
    # Delete frame files if exist
    if animation.frame_paths:
        for frame_path in animation.frame_paths:
            if Path(frame_path).exists():
                Path(frame_path).unlink()
    
    # Delete database record
    db.delete(animation)
    db.commit()
    
    return {
        "message": f"Animation sequence {animation_id} deleted successfully",
        "animation_id": animation_id
    }
