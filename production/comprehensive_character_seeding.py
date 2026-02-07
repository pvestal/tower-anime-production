#!/usr/bin/env python3
"""
Comprehensive Character Seeding System
Extracts, analyzes, and seeds training data for all Mario Galaxy characters
"""

import os
import json
import shutil
from pathlib import Path
from collections import defaultdict
import cv2
import numpy as np

class ComprehensiveCharacterSeeder:
    def __init__(self):
        self.base_dir = Path("/mnt/1TB-storage")
        self.characters = ["mario", "luigi", "bowser_jr", "princess_peach", "rosalina"]
        self.sources = {
            "existing_datasets": self.base_dir / "lora_datasets",
            "video_frames": self.base_dir / "training_videos/mario_galaxy",
            "comfyui_output": self.base_dir / "ComfyUI/output",
            "trailer_frames": self.base_dir / "lora_datasets/bowser_jr_movie_2026/images"
        }
        self.output_dir = self.base_dir / "comprehensive_seed_datasets"
        self.stats = defaultdict(lambda: defaultdict(int))

    def analyze_all_sources(self):
        """Analyze all available image sources"""
        print("=" * 60)
        print("🔍 COMPREHENSIVE CHARACTER DATA ANALYSIS")
        print("=" * 60)

        for character in self.characters:
            print(f"\n📦 Analyzing {character.upper()}:")
            print("-" * 40)

            # Check existing LoRA datasets
            for pattern in [f"*{character}*/images/*.png", f"*{character}*/images/*.jpg"]:
                files = list(self.sources["existing_datasets"].glob(pattern))
                if files:
                    self.stats[character]["lora_datasets"] = len(files)
                    print(f"  LoRA Datasets: {len(files)} images")

            # Check video frames
            char_frames_dir = self.sources["video_frames"] / "character_analysis" / character
            if char_frames_dir.exists():
                frames = list(char_frames_dir.glob("*.jpg"))
                self.stats[character]["video_frames"] = len(frames)
                print(f"  Video Frames: {len(frames)} frames")

            # Check ComfyUI outputs
            comfy_files = list(self.sources["comfyui_output"].glob(f"*{character}*.png"))
            if comfy_files:
                self.stats[character]["comfyui"] = len(comfy_files)
                print(f"  ComfyUI Generated: {len(comfy_files)} images")

            # Check for any other sources
            total = sum(self.stats[character].values())
            print(f"  📊 TOTAL: {total} images available")

            if total == 0:
                print(f"  ⚠️ WARNING: No data found for {character}")
            elif total < 10:
                print(f"  ⚠️ WARNING: Only {total} images - need more for training")
            else:
                print(f"  ✅ Sufficient data for initial training")

    def compare_datasets(self):
        """Compare existing datasets with requirements"""
        print("\n" + "=" * 60)
        print("📊 DATASET COMPARISON & REQUIREMENTS")
        print("=" * 60)

        requirements = {
            "bowser_jr": {
                "required_features": ["RED BLOODSHOT EYES", "orange mohawk", "green shell"],
                "min_images": 20,
                "priority": "CRITICAL"
            },
            "mario": {
                "required_features": ["red cap", "blue overalls", "mustache"],
                "min_images": 20,
                "priority": "HIGH"
            },
            "luigi": {
                "required_features": ["green cap", "blue overalls", "tall"],
                "min_images": 20,
                "priority": "HIGH"
            },
            "princess_peach": {
                "required_features": ["pink dress", "blonde hair", "crown"],
                "min_images": 15,
                "priority": "MEDIUM"
            },
            "rosalina": {
                "required_features": ["cyan dress", "platinum hair", "star wand"],
                "min_images": 15,
                "priority": "MEDIUM"
            }
        }

        for character, req in requirements.items():
            total = sum(self.stats[character].values())
            print(f"\n{character.upper()}:")
            print(f"  Priority: {req['priority']}")
            print(f"  Required: {req['min_images']} images")
            print(f"  Available: {total} images")
            print(f"  Status: {'✅ READY' if total >= req['min_images'] else f'❌ NEED {req['min_images'] - total} MORE'}")
            print(f"  Required Features: {', '.join(req['required_features'])}")

            if character == "bowser_jr":
                print("  ⚠️ CRITICAL: Must verify RED BLOODSHOT EYES in all images!")

    def build_seed_datasets(self):
        """Build comprehensive seed datasets for each character"""
        print("\n" + "=" * 60)
        print("🔨 BUILDING SEED DATASETS")
        print("=" * 60)

        for character in self.characters:
            print(f"\n🎮 Building dataset for {character.upper()}:")

            char_output = self.output_dir / character / "images"
            char_output.mkdir(parents=True, exist_ok=True)

            copied = 0

            # Copy from best sources
            # 1. Clean LoRA datasets (highest quality)
            clean_dir = self.sources["existing_datasets"] / f"clean_mario_galaxy_{character}" / "images"
            if clean_dir.exists():
                for img in list(clean_dir.glob("*.png"))[:10]:
                    dst = char_output / f"{character}_{copied:04d}.png"
                    shutil.copy(img, dst)
                    self.create_caption(dst, character)
                    copied += 1
                    print(f"  Copied from clean dataset: {img.name}")

            # 2. Regular LoRA datasets
            regular_dir = self.sources["existing_datasets"] / f"mario_galaxy_{character}" / "images"
            if regular_dir.exists() and copied < 20:
                for img in list(regular_dir.glob("*.png"))[:10]:
                    dst = char_output / f"{character}_{copied:04d}.png"
                    shutil.copy(img, dst)
                    self.create_caption(dst, character)
                    copied += 1

            # 3. Video frames (if needed)
            if copied < 20:
                frames_dir = self.sources["video_frames"] / "character_analysis" / character
                if frames_dir.exists():
                    for frame in list(frames_dir.glob("*.jpg"))[:5]:
                        dst = char_output / f"{character}_{copied:04d}.jpg"
                        shutil.copy(frame, dst)
                        self.create_caption(dst, character)
                        copied += 1

            print(f"  ✅ Created seed dataset with {copied} images")
            print(f"  📁 Location: {char_output}")

            # Create metadata
            metadata = {
                "character": character,
                "total_images": copied,
                "sources": {
                    "clean_lora": min(10, len(list(clean_dir.glob("*.png")))) if clean_dir.exists() else 0,
                    "regular_lora": min(10, len(list(regular_dir.glob("*.png")))) if regular_dir.exists() else 0,
                    "video_frames": copied - min(20, copied)
                },
                "ready_for_training": copied >= 10
            }

            metadata_file = self.output_dir / character / "metadata.json"
            metadata_file.write_text(json.dumps(metadata, indent=2))

    def create_caption(self, image_path, character):
        """Create appropriate caption for character"""
        captions = {
            "bowser_jr": "Bowser Jr, Illumination 3D movie style, small koopa villain, orange mohawk, RED BLOODSHOT EYES, green shell, sharp teeth",
            "mario": "Mario, Illumination 3D movie style, red cap, blue overalls, brown mustache, friendly hero",
            "luigi": "Luigi, Illumination 3D movie style, green cap, blue overalls, tall, nervous sidekick",
            "princess_peach": "Princess Peach, Illumination 3D movie style, pink dress, blonde hair, crown, elegant",
            "rosalina": "Rosalina, Illumination 3D movie style, cyan dress, platinum hair, star wand, cosmic guardian"
        }

        caption_file = Path(str(image_path).replace('.png', '.txt').replace('.jpg', '.txt'))
        caption_file.write_text(captions.get(character, f"{character}, 3D movie style character"))

    def generate_report(self):
        """Generate comprehensive seeding report"""
        print("\n" + "=" * 60)
        print("📋 FINAL SEEDING REPORT")
        print("=" * 60)

        report = {
            "timestamp": "2026-01-29",
            "characters_analyzed": len(self.characters),
            "total_images_found": sum(sum(self.stats[c].values()) for c in self.characters),
            "characters_ready": [],
            "characters_need_more": [],
            "critical_issues": [],
            "recommendations": []
        }

        for character in self.characters:
            total = sum(self.stats[character].values())
            seed_dir = self.output_dir / character / "images"
            seed_count = len(list(seed_dir.glob("*"))) if seed_dir.exists() else 0

            if seed_count >= 10:
                report["characters_ready"].append({
                    "name": character,
                    "seed_images": seed_count,
                    "total_available": total
                })
            else:
                report["characters_need_more"].append({
                    "name": character,
                    "seed_images": seed_count,
                    "needed": 10 - seed_count
                })

        if "bowser_jr" in [c["name"] for c in report["characters_ready"]]:
            report["critical_issues"].append(
                "Bowser Jr images have BLACK eyes - need manual correction to RED BLOODSHOT EYES"
            )

        report["recommendations"] = [
            "1. Manually verify Bowser Jr eye color in all images",
            "2. Generate additional Princess Peach and Rosalina images if needed",
            "3. Use img2img to correct eye colors where necessary",
            "4. Start LoRA training with characters that have 10+ verified images"
        ]

        # Save report
        report_file = self.output_dir / "seeding_report.json"
        report_file.write_text(json.dumps(report, indent=2))

        # Print summary
        print("\n📊 SUMMARY:")
        print(f"  Total Images Found: {report['total_images_found']}")
        print(f"  Characters Ready: {len(report['characters_ready'])}")
        print(f"  Characters Need More: {len(report['characters_need_more'])}")

        if report["characters_ready"]:
            print("\n✅ READY FOR TRAINING:")
            for char in report["characters_ready"]:
                print(f"  - {char['name']}: {char['seed_images']} seed images")

        if report["characters_need_more"]:
            print("\n❌ NEED MORE DATA:")
            for char in report["characters_need_more"]:
                print(f"  - {char['name']}: need {char['needed']} more images")

        if report["critical_issues"]:
            print("\n⚠️ CRITICAL ISSUES:")
            for issue in report["critical_issues"]:
                print(f"  - {issue}")

        print("\n📁 All seed datasets saved to:")
        print(f"   {self.output_dir}")

    def run(self):
        """Run complete seeding process"""
        print("\n🚀 Starting Comprehensive Character Seeding Process")
        print("=" * 60)

        # Step 1: Analyze all sources
        self.analyze_all_sources()

        # Step 2: Compare with requirements
        self.compare_datasets()

        # Step 3: Build seed datasets
        self.build_seed_datasets()

        # Step 4: Generate report
        self.generate_report()

        print("\n✅ Seeding process complete!")
        print("\nNext steps:")
        print("1. Review seed datasets in: /mnt/1TB-storage/comprehensive_seed_datasets/")
        print("2. Verify Bowser Jr images for RED EYES")
        print("3. Start LoRA training for ready characters")
        print("4. Generate additional images for incomplete characters")

if __name__ == "__main__":
    seeder = ComprehensiveCharacterSeeder()
    seeder.run()