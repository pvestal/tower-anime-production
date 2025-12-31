#!/usr/bin/env python3
"""
Run the complete production pipeline for one pose
"""
import sys
from pathlib import Path
from workflows.tokyo_debt_production import TokyoDebtProduction

def main():
    # 1. Choose a pose skeleton
    pose_skeleton = sys.argv[1] if len(sys.argv) > 1 else "standing"
    skeleton_path = Path(f"/opt/tower-anime-production/poses/mei_{pose_skeleton}_skeleton.png")

    if not skeleton_path.exists():
        print(f"❌ Pose skeleton not found: {skeleton_path}")
        print("\n📋 Available poses:")
        for p in Path("/opt/tower-anime-production/poses").glob("mei_*_skeleton.png"):
            pose_name = p.stem.replace("mei_", "").replace("_skeleton", "")
            print(f"   • {pose_name}")
        sys.exit(1)

    # 2. Initialize production
    print("=" * 60)
    print(f"🎬 TOKYO DEBT PRODUCTION: {pose_skeleton.upper()} POSE")
    print("=" * 60)
    print(f"Skeleton: {skeleton_path.name}")
    print(f"Canonical: Mei_Tokyo_Debt_SVD_smooth_00001.png")
    print()

    producer = TokyoDebtProduction()

    # 3. Generate pose variation
    print("Stage 1: Generating pose variation...")
    pose_image = producer.generate_pose_variation(
        pose_type=pose_skeleton,
        denoise=0.4,  # Proven to work
        controlnet_strength=0.7
    )

    if not pose_image:
        print("❌ Pose generation failed")
        sys.exit(1)

    print(f"✅ Pose generated: {Path(pose_image).name}")

    # 4. Generate SVD video
    print("\nStage 2: Generating SVD video...")
    video = producer.generate_svd_video(
        base_image=pose_image,
        motion_bucket=127,
        fps=8
    )

    if video:
        print(f"✅ Video generated: {Path(video).name}")
        print("\n" + "=" * 60)
        print("✅ PRODUCTION COMPLETE")
        print("=" * 60)
        print(f"Pose:  {pose_image}")
        print(f"Video: {video}")
    else:
        print("❌ Video generation failed")

if __name__ == "__main__":
    main()