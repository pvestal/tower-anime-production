#!/usr/bin/env python3
"""
Check consistency scores for generated images using CharacterConsistencyService
Measures similarity between generated images and reference Mei image
"""
import asyncio
import sys
import os
sys.path.append('/opt/tower-anime-production')

from pathlib import Path
import asyncpg
from services.character_consistency_v2 import CharacterConsistencyService
import glob
from datetime import datetime

DB_CONFIG = {
    'host': 'localhost',
    'database': 'anime_production',
    'user': 'patrick',
    'password': 'tower_echo_brain_secret_key_2025'
}

async def check_consistency():
    """Check consistency scores for all phase1_tune images"""

    # Connect to database
    pool = await asyncpg.create_pool(**DB_CONFIG)

    # Initialize consistency service
    consistency_service = CharacterConsistencyService(
        db_pool=pool,
        similarity_threshold=0.70,
        device="cuda"
    )

    await consistency_service.initialize()

    # Find reference image (first Mei image we can find)
    reference_paths = [
        "/mnt/1TB-storage/ComfyUI/output/Mei*.png",
        "/mnt/1TB-storage/outputs/mei_reference.png",
        "/mnt/1TB-storage/ComfyUI/output/phase1_tune_mei_original*.png"
    ]

    reference_img = None
    for pattern in reference_paths:
        matches = glob.glob(pattern)
        if matches:
            reference_img = matches[0]
            break

    if not reference_img:
        print("❌ No reference Mei image found. Generate one first.")
        await pool.close()
        return

    print(f"📸 Using reference image: {reference_img}")

    # Compute reference embedding
    ref_embedding = await consistency_service.compute_embedding(reference_img)
    if ref_embedding is None:
        print("❌ Could not compute embedding for reference image")
        await pool.close()
        return

    # Find all test images
    test_pattern = "/mnt/1TB-storage/ComfyUI/output/phase1_tune_*.png"
    test_images = sorted(glob.glob(test_pattern), key=os.path.getmtime, reverse=True)[:10]

    if not test_images:
        print("❌ No test images found. Run phase1_lora_tuning.py first.")
        await pool.close()
        return

    print(f"\n🔍 Checking consistency for {len(test_images)} images...")
    print("=" * 60)

    results = []
    for img_path in test_images:
        filename = os.path.basename(img_path)

        # Extract profile name from filename
        if "high_lora" in filename:
            profile = "High LoRA (1.0)"
        elif "face_focus" in filename:
            profile = "Face Focus (0.9)"
        elif "original" in filename:
            profile = "Original (0.7)"
        else:
            profile = filename

        # Compute test embedding
        test_embedding = await consistency_service.compute_embedding(img_path)

        if test_embedding is None:
            print(f"⚠️  {profile:<20} - No face detected")
            continue

        # Calculate similarity
        similarity = consistency_service._cosine_similarity(ref_embedding, test_embedding)
        passes = similarity >= 0.70

        results.append({
            'profile': profile,
            'similarity': similarity,
            'passes': passes,
            'path': img_path
        })

        status = "✅ PASS" if passes else "❌ FAIL"
        print(f"{status} {profile:<20} - Similarity: {similarity:.3f}")

    # Summary
    print("\n📊 CONSISTENCY ANALYSIS SUMMARY")
    print("=" * 60)
    print(f"Threshold: 0.70")
    print(f"Reference: {os.path.basename(reference_img)}")

    if results:
        best = max(results, key=lambda x: x['similarity'])
        worst = min(results, key=lambda x: x['similarity'])
        avg_sim = sum(r['similarity'] for r in results) / len(results)
        pass_rate = sum(1 for r in results if r['passes']) / len(results) * 100

        print(f"\nBest:  {best['profile']} ({best['similarity']:.3f})")
        print(f"Worst: {worst['profile']} ({worst['similarity']:.3f})")
        print(f"Average Similarity: {avg_sim:.3f}")
        print(f"Pass Rate: {pass_rate:.0f}%")

        # Recommendations
        print("\n💡 RECOMMENDATIONS:")
        if best['similarity'] >= 0.70:
            print(f"✅ Use settings from '{best['profile']}' for consistent generation")

            # Update database recommendation
            if "1.0" in best['profile']:
                print("\n🔧 To apply best settings, run:")
                print("""
export PGPASSWORD='tower_echo_brain_secret_key_2025'
psql -h localhost -U patrick -d anime_production -c "
UPDATE generation_profiles
SET lora_strength = 1.0, cfg_scale = 7.5, steps = 30
WHERE name = 'mei_default';"
""")
        else:
            print("⚠️  All configurations below threshold. Consider:")
            print("  1. Increase LoRA strength to 1.1-1.2")
            print("  2. Check LoRA training quality")
            print("  3. Use different base checkpoint")
            print("  4. Add IPAdapter for face consistency")

    await pool.close()

if __name__ == "__main__":
    asyncio.run(check_consistency())