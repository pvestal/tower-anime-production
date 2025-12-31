#!/usr/bin/env python3
"""
Create pose skeleton library for production
"""
import shutil
from pathlib import Path

POSES_DIR = Path("/opt/tower-anime-production/poses")
POSES_DIR.mkdir(exist_ok=True)

# For now, copy existing skeletons we've generated
existing_skeletons = [
    ("/mnt/1TB-storage/ComfyUI/output/CANONICAL_skeleton_00001_.png", "standing"),
    ("/mnt/1TB-storage/ComfyUI/output/POSE_frontal_00002_.png", "frontal"),
    ("/mnt/1TB-storage/ComfyUI/output/POSE_professional_00001_.png", "professional"),
    ("/mnt/1TB-storage/ComfyUI/output/skeleton_professional_00001_.png", "professional_alt")
]

print("📚 Creating pose skeleton library...")

for source, name in existing_skeletons:
    source_path = Path(source)
    if source_path.exists():
        dest = POSES_DIR / f"mei_{name}_skeleton.png"
        shutil.copy2(source_path, dest)
        print(f"   ✅ {name}: {dest.name}")
    else:
        print(f"   ❌ {name}: Source not found")

# List available poses
print("\n📋 Available poses:")
for pose in POSES_DIR.glob("*.png"):
    print(f"   • {pose.stem.replace('mei_', '').replace('_skeleton', '')}")