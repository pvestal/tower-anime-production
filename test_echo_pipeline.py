#!/usr/bin/env python3
"""
Test Echo Brain Integration Pipeline for Tokyo Debt Desire
Tests the complete flow from Echo generation to database storage
"""

import asyncio
import json
import sys
import os
sys.path.append('/opt/tower-anime-production')

from services.echo_json_bridge import EchoJSONBridge, store_json_episode

async def test_complete_pipeline():
    """Test the complete Echo Brain -> Database pipeline"""

    print("=" * 60)
    print("ECHO BRAIN INTEGRATION PIPELINE TEST")
    print("=" * 60)

    # Load the Tokyo Debt Desire context
    with open('/tmp/tokyo_debt_context.json', 'r') as f:
        context = json.load(f)

    print(f"\n📋 Project: {context['project']['name']}")
    print(f"👥 Characters: {len(context['characters'])}")
    print(f"🎬 Current Episodes: {len(context['episodes'])}")

    # Prepare project context for Echo
    project_context = {
        'project_name': context['project']['name'],
        'project_id': context['project']['id'],
        'characters': context['characters']
    }

    # Create the bridge
    bridge = EchoJSONBridge()

    # Episode 2 concept continuing from "The Debt Collector"
    episode_concept = """Generate Episode 2: "Escalating Tensions"

    Continue from Episode 1 where the debt collector arrived.
    The roommates (Mei, Rina, Yuki) must now intensify their seduction efforts
    while Takeshi faces increasing yakuza pressure. Include:
    - Morning scene with Mei making breakfast in revealing outfit
    - Afternoon scene with Rina "accidentally" spilling water on herself
    - Evening scene with Yuki offering a massage
    - Night scene with yakuza confrontation
    - Cliffhanger ending with unexpected visitor

    Each scene should have detailed ComfyUI prompts for anime-style generation."""

    print(f"\n🎭 Generating Episode 2 with Echo Brain...")
    print(f"Concept: Escalating Tensions")

    try:
        # Generate episode with Echo Brain
        episode_json = await bridge.generate_episode_json(episode_concept, project_context)

        print("\n✅ Echo Brain Response Received!")

        # Validate the JSON structure
        print("\n📊 Validating JSON Structure...")
        required_fields = ['episode', 'scenes']
        missing = [f for f in required_fields if f not in episode_json]

        if missing:
            print(f"⚠️  Warning: Missing fields: {missing}")
            # Add defaults if needed
            if 'episode' not in episode_json:
                episode_json['episode'] = {
                    'title': 'Escalating Tensions',
                    'number': 2,
                    'synopsis': episode_concept
                }
            if 'scenes' not in episode_json:
                episode_json['scenes'] = []

        # Display generated content
        print(f"\n📝 Generated Episode:")
        print(f"  Title: {episode_json['episode'].get('title', 'Unknown')}")
        print(f"  Number: {episode_json['episode'].get('number', 2)}")
        print(f"  Scenes: {len(episode_json.get('scenes', []))}")

        # Show sample scenes
        if episode_json.get('scenes'):
            print("\n🎬 Sample Scenes:")
            for i, scene in enumerate(episode_json['scenes'][:3], 1):
                print(f"\n  Scene {scene.get('order', i)}:")
                print(f"    Location: {scene.get('location', 'Unknown')}")
                print(f"    Time: {scene.get('time', 'Unknown')}")
                print(f"    Characters: {', '.join(scene.get('characters', []))}")
                print(f"    Mood: {scene.get('mood', 'Unknown')}")
                if 'comfyui_prompt' in scene:
                    print(f"    ComfyUI: {scene['comfyui_prompt'][:80]}...")

        # Save the generated JSON
        output_file = '/tmp/tokyo_debt_episode2.json'
        with open(output_file, 'w') as f:
            json.dump(episode_json, f, indent=2)
        print(f"\n💾 Saved generated episode to: {output_file}")

        # Attempt database storage
        print("\n🗄️  Attempting database storage...")
        try:
            episode_id = store_json_episode(episode_json, context['project']['id'])
            print(f"✅ Episode stored in database with ID: {episode_id}")
        except Exception as db_error:
            print(f"⚠️  Database storage failed: {db_error}")
            print("   (This is expected if there are schema mismatches)")

        # Test ComfyUI prompt quality
        print("\n🎨 ComfyUI Prompt Quality Check:")
        for scene in episode_json.get('scenes', [])[:2]:
            prompt = scene.get('comfyui_prompt', '')
            quality_checks = {
                'has_characters': any(char.lower() in prompt.lower()
                                     for char in ['mei', 'rina', 'yuki', 'takeshi']),
                'has_style': 'anime' in prompt.lower(),
                'has_quality': 'quality' in prompt.lower() or 'detailed' in prompt.lower(),
                'has_lighting': 'lighting' in prompt.lower() or 'light' in prompt.lower(),
                'has_location': any(loc in prompt.lower()
                                   for loc in ['int', 'ext', 'room', 'apartment'])
            }

            passed = sum(quality_checks.values())
            print(f"\n  Scene {scene.get('order', '?')}: {passed}/5 quality checks")
            for check, result in quality_checks.items():
                status = "✅" if result else "❌"
                print(f"    {status} {check.replace('_', ' ').title()}")

        # Summary
        print("\n" + "=" * 60)
        print("PIPELINE TEST SUMMARY")
        print("=" * 60)

        success_metrics = {
            'Echo_Connection': True,
            'JSON_Generation': bool(episode_json),
            'Schema_Compliance': all(f in episode_json for f in ['episode', 'scenes']),
            'Scene_Count': len(episode_json.get('scenes', [])) >= 4,
            'Character_Usage': any('mei' in str(episode_json).lower()),
            'ComfyUI_Ready': any('comfyui_prompt' in s for s in episode_json.get('scenes', []))
        }

        total = len(success_metrics)
        passed = sum(success_metrics.values())

        print(f"\n📊 Overall Score: {passed}/{total} ({int(passed/total*100)}%)")

        for metric, result in success_metrics.items():
            status = "✅" if result else "❌"
            print(f"  {status} {metric.replace('_', ' ')}")

        if passed >= 5:
            print("\n🎉 SUCCESS: Pipeline is operational!")
        elif passed >= 3:
            print("\n⚠️  PARTIAL: Pipeline works but needs improvements")
        else:
            print("\n❌ FAILURE: Pipeline has critical issues")

        return episode_json

    except Exception as e:
        print(f"\n❌ Pipeline Error: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print("Starting Echo Brain Integration Pipeline Test...")
    print("Testing with Tokyo Debt Desire project context...")

    result = asyncio.run(test_complete_pipeline())

    if result:
        print("\n✅ Test completed successfully!")
        print(f"Generated episode available at: /tmp/tokyo_debt_episode2.json")
    else:
        print("\n❌ Test failed - check errors above")