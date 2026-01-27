#!/usr/bin/env python3
"""
Generate all three main characters with accurate descriptions
"""

import asyncio
from character_accurate_pipeline import CharacterAccuratePipeline

async def main():
    pipeline = CharacterAccuratePipeline()

    # Generate Luna Chen
    print("🔬 Generating Luna Chen - AI Researcher")
    luna = await pipeline.generate_accurate_character_image(
        "Luna Chen",
        scene_context="in futuristic laboratory with holographic displays, cyberpunk setting"
    )

    if luna:
        print(f"✅ Luna generated: {luna}")
        luna_video = await pipeline.generate_character_video_sequence(
            "Luna Chen",
            "working with holographic data displays in high-tech lab"
        )
        if luna_video:
            print(f"✅ Luna video: {luna_video}")

    # Generate Viktor Kozlov
    print("\n💼 Generating Viktor Kozlov - Corporate Antagonist")
    viktor = await pipeline.generate_accurate_character_image(
        "Viktor Kozlov",
        scene_context="in corporate boardroom overlooking cyberpunk city skyline"
    )

    if viktor:
        print(f"✅ Viktor generated: {viktor}")
        viktor_video = await pipeline.generate_character_video_sequence(
            "Viktor Kozlov",
            "walking through corporate headquarters, augmented reality displays around"
        )
        if viktor_video:
            print(f"✅ Viktor video: {viktor_video}")

    # Verify Akira exists
    print("\n🏍️ Verifying Akira Yamamoto")
    akira_files = list(pipeline.output_dir.glob("accurate_*Akira*.png"))
    if akira_files:
        print(f"✅ Akira already generated: {len(akira_files)} files")

    print("\n" + "="*50)
    print("CHARACTER GENERATION COMPLETE")
    print("="*50)

    # Summary
    characters_ready = []
    if akira_files:
        characters_ready.append("Akira Yamamoto ✅")
    if luna:
        characters_ready.append("Luna Chen ✅")
    if viktor:
        characters_ready.append("Viktor Kozlov ✅")

    print(f"Characters ready: {len(characters_ready)}/3")
    for char in characters_ready:
        print(f"  - {char}")

if __name__ == "__main__":
    asyncio.run(main())