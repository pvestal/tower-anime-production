"""
Fixed animation status endpoint that actually works
Queries ComfyUI history API with the stored prompt_id
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import httpx

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_db
from models import AnimationSequence

router = APIRouter(prefix="/api/anime/animation", tags=["animation-status"])

COMFYUI_URL = "http://127.0.0.1:8188"

@router.get("/status/{animation_id}")
async def get_animation_status_fixed(
    animation_id: int,
    db: Session = Depends(get_db)
):
    """
    Get ACTUAL status from ComfyUI history API
    No more fake statuses
    """
    # Get animation from database
    animation = db.query(AnimationSequence).filter(
        AnimationSequence.id == animation_id
    ).first()
    
    if not animation:
        raise HTTPException(status_code=404, detail="Animation not found")
    
    # Get ComfyUI prompt_id from metadata
    if not animation.metadata_ or "comfyui_prompt_id" not in animation.metadata_:
        return {
            "animation_id": animation.id,
            "status": animation.status,
            "error": "No ComfyUI prompt_id found in metadata"
        }
    
    prompt_id = animation.metadata_["comfyui_prompt_id"]
    
    # Query ComfyUI history API
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{COMFYUI_URL}/history/{prompt_id}")
            response.raise_for_status()
            history = response.json()
            
            if prompt_id not in history:
                return {
                    "animation_id": animation.id,
                    "status": "submitted",
                    "comfyui_status": "not_in_history_yet"
                }
            
            result = history[prompt_id]
            comfyui_status = result.get("status", {}).get("status_str", "unknown")
            outputs = result.get("outputs", {})
            
            # Update database if completed
            if outputs and animation.status != "completed":
                animation.status = "completed"
                animation.metadata_["outputs"] = outputs
                
                # Extract frame paths from outputs
                frame_paths = []
                for node_id, output_data in outputs.items():
                    if "images" in output_data:
                        for img in output_data["images"]:
                            frame_paths.append(f"/mnt/1TB-storage/ComfyUI/output/{img['filename']}")
                
                animation.frame_paths = frame_paths
                animation.frame_count = len(frame_paths)
                db.commit()
            
            return {
                "animation_id": animation.id,
                "status": animation.status,
                "comfyui_status": comfyui_status,
                "comfyui_prompt_id": prompt_id,
                "outputs": outputs,
                "frame_count": len(animation.frame_paths) if animation.frame_paths else 0,
                "frame_paths": animation.frame_paths
            }
            
    except Exception as e:
        return {
            "animation_id": animation.id,
            "status": animation.status,
            "error": f"ComfyUI query failed: {str(e)}"
        }
