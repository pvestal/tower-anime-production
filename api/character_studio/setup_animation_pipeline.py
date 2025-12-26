#!/usr/bin/env python3
"""
setup_animation_pipeline.py
Phase 3 Animation Pipeline Setup Script

Creates necessary directories, sample pose sequences, and validates configuration.
Run this after deploying Phase 3 to set up the animation system.
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_directory_structure() -> Dict[str, Path]:
    """
    Create all necessary directories for animation pipeline
    Returns dict of directory paths
    """
    logger.info("Creating directory structure...")
    
    base_dirs = {
        "poses": Path("/mnt/1TB-storage/poses"),
        "workflows": Path("/opt/tower-anime-production/workflows/animation_templates"),
        "output": Path("/mnt/1TB-storage/ComfyUI/output"),
        "temp": Path("/tmp/animation_frames")
    }
    
    # Create main pose subdirectories
    pose_subdirs = [
        "walk_cycle_12f",
        "idle_breathing_8f",
        "mouth_shapes_8f",
        "custom"
    ]
    
    for dir_name, dir_path in base_dirs.items():
        dir_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"✓ Created {dir_name}: {dir_path}")
    
    # Create pose subdirectories
    for subdir in pose_subdirs:
        pose_dir = base_dirs["poses"] / subdir
        pose_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"✓ Created pose subdir: {pose_dir}")
    
    return base_dirs


def create_sample_poses() -> Dict[str, List[str]]:
    """
    Create sample pose reference files for animations
    Returns dict of pose sequences with file paths
    """
    logger.info("Creating sample pose sequences...")
    
    poses_base = Path("/mnt/1TB-storage/poses")
    pose_sequences = {}
    
    # 1. Walk Cycle (12 frames) - OpenPose skeleton
    walk_cycle_dir = poses_base / "walk_cycle_12f"
    walk_cycle_poses = []
    
    # Define walk cycle pose data (simplified OpenPose keypoints)
    walk_poses = [
        {"frame": 1, "description": "Contact - Right foot forward", "phase": "contact_right"},
        {"frame": 2, "description": "Recoil - Weight shift", "phase": "recoil_right"},
        {"frame": 3, "description": "Passing - Left leg passing", "phase": "passing_left"},
        {"frame": 4, "description": "High point - Left foot lifting", "phase": "high_left"},
        {"frame": 5, "description": "Contact - Left foot forward", "phase": "contact_left"},
        {"frame": 6, "description": "Recoil - Weight shift", "phase": "recoil_left"},
        {"frame": 7, "description": "Passing - Right leg passing", "phase": "passing_right"},
        {"frame": 8, "description": "High point - Right foot lifting", "phase": "high_right"},
        {"frame": 9, "description": "Contact - Right foot forward (repeat)", "phase": "contact_right"},
        {"frame": 10, "description": "Recoil - Weight shift", "phase": "recoil_right"},
        {"frame": 11, "description": "Passing - Left leg passing", "phase": "passing_left"},
        {"frame": 12, "description": "High point - Left foot lifting", "phase": "high_left"}
    ]
    
    for pose_data in walk_poses:
        pose_file = walk_cycle_dir / f"walk_frame_{pose_data['frame']:02d}.json"
        pose_metadata = {
            "frame_number": pose_data["frame"],
            "description": pose_data["description"],
            "phase": pose_data["phase"],
            "pose_type": "openpose",
            "keypoints": "placeholder - actual OpenPose JSON would go here",
            "note": "This is a placeholder. Replace with actual OpenPose keypoint data."
        }
        
        with open(pose_file, 'w') as f:
            json.dump(pose_metadata, f, indent=2)
        
        walk_cycle_poses.append(str(pose_file))
    
    pose_sequences["walk_cycle_12f"] = walk_cycle_poses
    logger.info(f"✓ Created {len(walk_cycle_poses)} walk cycle poses")
    
    # 2. Idle Breathing (8 frames) - Depth map
    idle_dir = poses_base / "idle_breathing_8f"
    idle_poses = []
    
    breathing_cycle = [
        {"frame": 1, "phase": "exhale_complete", "chest_depth": 0.0},
        {"frame": 2, "phase": "inhale_start", "chest_depth": 0.2},
        {"frame": 3, "phase": "inhale_mid", "chest_depth": 0.5},
        {"frame": 4, "phase": "inhale_complete", "chest_depth": 1.0},
        {"frame": 5, "phase": "hold", "chest_depth": 1.0},
        {"frame": 6, "phase": "exhale_start", "chest_depth": 0.8},
        {"frame": 7, "phase": "exhale_mid", "chest_depth": 0.4},
        {"frame": 8, "phase": "exhale_end", "chest_depth": 0.1}
    ]
    
    for breath_data in breathing_cycle:
        pose_file = idle_dir / f"idle_frame_{breath_data['frame']:02d}.json"
        pose_metadata = {
            "frame_number": breath_data["frame"],
            "phase": breath_data["phase"],
            "chest_expansion": breath_data["chest_depth"],
            "pose_type": "depth_map",
            "depth_data": "placeholder - actual depth map would go here",
            "note": "This is a placeholder. Replace with actual depth map data."
        }
        
        with open(pose_file, 'w') as f:
            json.dump(pose_metadata, f, indent=2)
        
        idle_poses.append(str(pose_file))
    
    pose_sequences["idle_breathing_8f"] = idle_poses
    logger.info(f"✓ Created {len(idle_poses)} idle breathing poses")
    
    # 3. Mouth Shapes / Visemes (8 phonemes) - Canny edge
    mouth_dir = poses_base / "mouth_shapes_8f"
    mouth_poses = []
    
    visemes = [
        {"phoneme": "AH", "description": "Open mouth (father, hot)", "mouth_opening": 1.0},
        {"phoneme": "EE", "description": "Wide smile (see, me)", "mouth_opening": 0.3},
        {"phoneme": "OO", "description": "Rounded lips (food, you)", "mouth_opening": 0.5},
        {"phoneme": "OH", "description": "Rounded open (go, no)", "mouth_opening": 0.7},
        {"phoneme": "M", "description": "Lips closed (mom, me)", "mouth_opening": 0.0},
        {"phoneme": "F", "description": "Teeth on lip (five, off)", "mouth_opening": 0.2},
        {"phoneme": "TH", "description": "Tongue visible (the, this)", "mouth_opening": 0.4},
        {"phoneme": "L", "description": "Tongue up (love, hello)", "mouth_opening": 0.3}
    ]
    
    for idx, viseme_data in enumerate(visemes, 1):
        pose_file = mouth_dir / f"viseme_{viseme_data['phoneme'].lower()}.json"
        pose_metadata = {
            "viseme_id": idx,
            "phoneme": viseme_data["phoneme"],
            "description": viseme_data["description"],
            "mouth_opening": viseme_data["mouth_opening"],
            "pose_type": "canny_edge",
            "edge_data": "placeholder - actual Canny edge map would go here",
            "note": "This is a placeholder. Replace with actual Canny edge detection data."
        }
        
        with open(pose_file, 'w') as f:
            json.dump(pose_metadata, f, indent=2)
        
        mouth_poses.append(str(pose_file))
    
    pose_sequences["mouth_shapes_8f"] = mouth_poses
    logger.info(f"✓ Created {len(mouth_poses)} mouth shape visemes")
    
    # Create sequence metadata files
    for sequence_name, pose_files in pose_sequences.items():
        sequence_metadata = {
            "sequence_name": sequence_name,
            "pose_count": len(pose_files),
            "pose_files": pose_files,
            "created_by": "setup_animation_pipeline.py",
            "note": "Sample pose sequence - replace JSON placeholders with actual pose data"
        }
        
        metadata_file = poses_base / sequence_name / "sequence.json"
        with open(metadata_file, 'w') as f:
            json.dump(sequence_metadata, f, indent=2)
    
    return pose_sequences


def create_sample_templates():
    """
    Verify ComfyUI workflow templates exist
    Templates should already be created by previous step
    """
    logger.info("Verifying ComfyUI workflow templates...")
    
    templates_dir = Path("/opt/tower-anime-production/workflows/animation_templates")
    required_templates = [
        "walk_cycle_2d.json",
        "idle_breathing.json",
        "talking_visemes.json",
        "templates.json"
    ]
    
    all_exist = True
    for template_file in required_templates:
        template_path = templates_dir / template_file
        if template_path.exists():
            logger.info(f"✓ Template exists: {template_file}")
        else:
            logger.warning(f"✗ Template missing: {template_file}")
            all_exist = False
    
    return all_exist


def verify_dependencies():
    """
    Verify required dependencies and tools are available
    """
    logger.info("Verifying dependencies...")
    
    dependencies = {
        "FFmpeg": "ffmpeg",
        "FFprobe": "ffprobe"
    }
    
    all_available = True
    for name, command in dependencies.items():
        if os.system(f"which {command} > /dev/null 2>&1") == 0:
            logger.info(f"✓ {name} available")
        else:
            logger.warning(f"✗ {name} not found - install with: sudo apt-get install ffmpeg")
            all_available = False
    
    # Check Python packages
    try:
        import aiohttp
        logger.info("✓ aiohttp available")
    except ImportError:
        logger.warning("✗ aiohttp not found - install with: pip install aiohttp")
        all_available = False
    
    return all_available


def print_summary(pose_sequences: Dict[str, List[str]], templates_exist: bool, deps_available: bool):
    """
    Print setup summary
    """
    logger.info("\n" + "="*60)
    logger.info("ANIMATION PIPELINE SETUP SUMMARY")
    logger.info("="*60)
    
    logger.info(f"\nPose Sequences Created:")
    for seq_name, poses in pose_sequences.items():
        logger.info(f"  • {seq_name}: {len(poses)} poses")
    
    logger.info(f"\nComfyUI Templates: {'✓ All present' if templates_exist else '✗ Some missing'}")
    logger.info(f"Dependencies: {'✓ All available' if deps_available else '✗ Some missing'}")
    
    logger.info("\n" + "="*60)
    logger.info("NEXT STEPS:")
    logger.info("="*60)
    logger.info("1. Replace pose JSON placeholders with actual pose data:")
    logger.info("   - OpenPose keypoints for walk cycle")
    logger.info("   - Depth maps for idle breathing")
    logger.info("   - Canny edges for mouth shapes")
    logger.info("\n2. Test animation generation:")
    logger.info("   curl -X POST https://vestal-garcia.duckdns.org/api/anime/animation/generate \\")
    logger.info("     -H 'Content-Type: application/json' \\")
    logger.info("     -d '{\"character_id\": 1, \"animation_type\": \"walk_cycle_2d\"}' -k")
    logger.info("\n3. Monitor animation status:")
    logger.info("   curl https://vestal-garcia.duckdns.org/api/anime/animation/status/<animation_id> -k")
    logger.info("="*60 + "\n")


def setup_animation_pipeline():
    """
    Main setup function - orchestrates all setup tasks
    """
    logger.info("Starting Animation Pipeline Setup...")
    logger.info("="*60 + "\n")
    
    try:
        # Create directories
        dirs = create_directory_structure()
        
        # Create sample poses
        pose_sequences = create_sample_poses()
        
        # Verify templates
        templates_exist = create_sample_templates()
        
        # Verify dependencies
        deps_available = verify_dependencies()
        
        # Print summary
        print_summary(pose_sequences, templates_exist, deps_available)
        
        logger.info("✓ Animation pipeline setup complete!\n")
        return True
        
    except Exception as e:
        logger.error(f"Setup failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = setup_animation_pipeline()
    sys.exit(0 if success else 1)
