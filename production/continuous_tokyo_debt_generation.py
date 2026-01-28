#!/usr/bin/env python3
"""
Continuous Tokyo Debt Desire Character Generation Service
Generates photorealistic character variations automatically with different poses, outfits, and scenes
"""

import asyncio
import logging
import random
import time
from pathlib import Path
from tokyo_debt_desire_pipeline import TokyoDebtDesirePipeline

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ContinuousTokyoDebtGenerator:
    """Continuous generation service for Tokyo Debt Desire characters"""

    def __init__(self):
        self.pipeline = TokyoDebtDesirePipeline()
        self.characters = [
            "Mei Kobayashi",
            "Rina Suzuki",
            "Takeshi Sato",
            "Yuki Tanaka"
        ]

        # Diverse scenes for photorealistic generation
        self.scenes = [
            "professional portrait in modern office",
            "casual conversation at coffee shop",
            "walking through Tokyo streets at night",
            "sitting at home reading documents",
            "business meeting in conference room",
            "relaxing in apartment living room",
            "standing outside Tokyo skyscraper",
            "working late at desk with city view",
            "casual portrait with urban background",
            "formal business attire in elevator",
            "smartphone call in busy street",
            "looking out window with city lights",
            "sitting in modern Japanese restaurant",
            "walking through Shibuya crossing",
            "portrait with neon Tokyo backdrop"
        ]

        # Different outfit styles
        self.outfit_modifiers = [
            "business suit",
            "casual clothing",
            "smart casual outfit",
            "formal attire",
            "modern Japanese fashion",
            "professional dress",
            "contemporary style"
        ]

        # Expression variations
        self.expressions = [
            "confident expression",
            "thoughtful look",
            "subtle smile",
            "serious demeanor",
            "friendly appearance",
            "determined expression",
            "calm composure"
        ]

        self.generation_count = 0
        self.target_generations = 100  # Generate 100 variations
        self.delay_between_generations = 30  # 30 seconds between generations

    async def generate_character_variation(self):
        """Generate a single character variation"""

        # Randomly select character, scene, outfit, and expression
        character = random.choice(self.characters)
        base_scene = random.choice(self.scenes)
        outfit = random.choice(self.outfit_modifiers)
        expression = random.choice(self.expressions)

        # Combine scene elements for rich prompt
        full_scene = f"{base_scene}, {outfit}, {expression}, photorealistic, high detail, professional lighting"

        logger.info(f"🎌 Generating variation #{self.generation_count + 1}")
        logger.info(f"   Character: {character}")
        logger.info(f"   Scene: {full_scene}")

        try:
            # Generate with photorealistic style (realisticVision model)
            result = await self.pipeline.generate_tokyo_debt_character(
                character_name=character,
                scene=full_scene,
                content_rating="sfw",
                style="realistic"  # Uses realisticVision_v51.safetensors
            )

            if result:
                self.generation_count += 1
                logger.info(f"✅ SUCCESS: Generated {result}")
                logger.info(f"📊 Progress: {self.generation_count}/{self.target_generations}")
                return True
            else:
                logger.error(f"❌ FAILED: Generation failed for {character}")
                return False

        except Exception as e:
            logger.error(f"❌ ERROR: {e}")
            return False

    async def run_continuous_generation(self):
        """Run continuous generation service"""

        logger.info("🚀 Starting Continuous Tokyo Debt Desire Generation Service")
        logger.info(f"   Target: {self.target_generations} photorealistic character variations")
        logger.info(f"   Delay: {self.delay_between_generations} seconds between generations")
        logger.info(f"   Characters: {', '.join(self.characters)}")
        logger.info("=" * 80)

        successful_generations = 0
        failed_generations = 0

        while self.generation_count < self.target_generations:
            start_time = time.time()

            success = await self.generate_character_variation()

            if success:
                successful_generations += 1
            else:
                failed_generations += 1

            # Calculate and log statistics
            total_attempts = successful_generations + failed_generations
            success_rate = (successful_generations / total_attempts * 100) if total_attempts > 0 else 0
            generation_time = time.time() - start_time

            logger.info(f"📈 Stats: {success_rate:.1f}% success rate, {generation_time:.1f}s generation time")

            # Check if we've reached the target
            if self.generation_count >= self.target_generations:
                logger.info(f"🎉 COMPLETED: Generated {self.generation_count} character variations!")
                break

            # Wait before next generation
            logger.info(f"⏳ Waiting {self.delay_between_generations}s before next generation...")
            await asyncio.sleep(self.delay_between_generations)

        # Final summary
        logger.info("=" * 80)
        logger.info("📊 FINAL SUMMARY")
        logger.info("=" * 80)
        logger.info(f"✅ Successful generations: {successful_generations}")
        logger.info(f"❌ Failed generations: {failed_generations}")
        logger.info(f"📈 Final success rate: {success_rate:.1f}%")
        logger.info(f"🎯 Target reached: {self.generation_count >= self.target_generations}")

    async def run_batch_generation(self, count: int = 10):
        """Run a smaller batch of generations for testing"""

        original_target = self.target_generations
        self.target_generations = count

        logger.info(f"🔄 Running batch generation ({count} variations)")
        await self.run_continuous_generation()

        self.target_generations = original_target

async def main():
    """Main entry point"""
    generator = ContinuousTokyoDebtGenerator()

    # Start with a small batch for testing
    logger.info("🧪 Starting with test batch of 5 generations")
    await generator.run_batch_generation(5)

    # Ask if user wants to continue with full generation
    logger.info("\n" + "=" * 50)
    logger.info("Test batch completed! Ready for continuous generation.")
    logger.info("To run full continuous generation, call run_continuous_generation()")

if __name__ == "__main__":
    asyncio.run(main())