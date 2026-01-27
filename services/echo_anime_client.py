#!/usr/bin/env python3
"""
Echo Brain Anime AI Director Client
Integrates Tower Anime Production with Echo Brain's specialized anime module
"""

import json
import asyncio
import aiohttp
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class EchoAnimeConfig:
    """Configuration for Echo Brain Anime module"""
    base_url: str = "http://localhost:8309"
    anime_endpoint: str = "/api/echo/anime"
    timeout: int = 30
    enabled: bool = True


class EchoAnimeClient:
    """Client for Echo Brain's AI Director capabilities"""

    def __init__(self):
        self.config = EchoAnimeConfig()
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Async context manager entry"""
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._session:
            await self._session.close()

    def _get_url(self, endpoint: str) -> str:
        """Build full URL for endpoint"""
        return f"{self.config.base_url}{self.config.anime_endpoint}{endpoint}"

    async def plan_scene(
        self,
        session_id: str,
        scene_description: str,
        characters: List[str] = None,
        style_references: List[str] = None,
        duration: int = 10
    ) -> Dict[str, Any]:
        """
        Get AI-generated scene planning with shot breakdown

        Args:
            session_id: Current creative session ID
            scene_description: Natural language description of the scene
            characters: List of character names in the scene
            style_references: Visual style references
            duration: Target duration in seconds

        Returns:
            Scene plan with shot list, moods, and cinematic suggestions
        """
        try:
            if not self.config.enabled:
                return self._get_default_scene_plan()

            payload = {
                "session_id": session_id,
                "scene_description": scene_description,
                "characters_in_scene": characters or [],
                "style_references": style_references or [],
                "duration_seconds": duration
            }

            if not self._session:
                self._session = aiohttp.ClientSession()

            async with self._session.post(
                self._get_url("/scene/plan"),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Scene planned successfully for session {session_id}")
                    return data
                else:
                    logger.warning(f"Scene planning failed: {response.status}")
                    return self._get_default_scene_plan()

        except Exception as e:
            logger.error(f"Error planning scene: {e}")
            return self._get_default_scene_plan()

    async def refine_prompt(
        self,
        session_id: str,
        raw_prompt: str,
        character_name: Optional[str] = None,
        emotion: Optional[str] = None,
        camera_angle: Optional[str] = None,
        context_tags: List[str] = None
    ) -> Dict[str, Any]:
        """
        Enhance a basic prompt with cinematic and style details

        Args:
            session_id: Current creative session ID
            raw_prompt: Basic prompt to enhance
            character_name: Character in the scene
            emotion: Current emotional state
            camera_angle: Desired camera angle
            context_tags: Additional context tags

        Returns:
            Enhanced prompt with negative prompts and style keywords
        """
        try:
            if not self.config.enabled:
                return self._get_default_prompt_refinement(raw_prompt)

            payload = {
                "session_id": session_id,
                "raw_prompt": raw_prompt,
                "context_tags": context_tags or [],
                "character_name": character_name,
                "current_emotion": emotion,
                "camera_angle": camera_angle
            }

            if not self._session:
                self._session = aiohttp.ClientSession()

            async with self._session.post(
                self._get_url("/prompt/refine"),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Prompt refined for session {session_id}")
                    return data
                else:
                    logger.warning(f"Prompt refinement failed: {response.status}")
                    return self._get_default_prompt_refinement(raw_prompt)

        except Exception as e:
            logger.error(f"Error refining prompt: {e}")
            return self._get_default_prompt_refinement(raw_prompt)

    async def submit_feedback(
        self,
        session_id: str,
        generation_id: str,
        prompt_used: str,
        quality_scores: Dict[str, float],
        user_feedback: Optional[str] = None,
        context_tags: List[str] = None
    ) -> Dict[str, Any]:
        """
        Submit generation feedback for learning

        Args:
            session_id: Current creative session ID
            generation_id: ID of the generated content
            prompt_used: The prompt that was used
            quality_scores: Quality metrics (ssim, optical_flow, etc.)
            user_feedback: Optional human feedback
            context_tags: Context tags for categorization

        Returns:
            Learning insights and recommendations
        """
        try:
            if not self.config.enabled:
                return self._get_default_feedback_response()

            payload = {
                "session_id": session_id,
                "generation_id": generation_id,
                "prompt_used": prompt_used,
                "quality_scores": quality_scores,
                "user_feedback": user_feedback,
                "context_tags": context_tags or []
            }

            if not self._session:
                self._session = aiohttp.ClientSession()

            async with self._session.post(
                self._get_url("/feedback/learn"),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Feedback submitted for generation {generation_id}")
                    return data
                else:
                    logger.warning(f"Feedback submission failed: {response.status}")
                    return self._get_default_feedback_response()

        except Exception as e:
            logger.error(f"Error submitting feedback: {e}")
            return self._get_default_feedback_response()

    async def check_health(self) -> Dict[str, Any]:
        """Check if Echo Brain anime module is available"""
        try:
            if not self._session:
                self._session = aiohttp.ClientSession()

            # Test the scene/plan endpoint with minimal data
            test_payload = {
                "session_id": "health_check",
                "scene_description": "test"
            }

            async with self._session.post(
                self._get_url("/scene/plan"),
                json=test_payload,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status in [200, 422]:  # 422 means validation, but service is up
                    return {
                        "status": "operational",
                        "message": "Echo Brain anime module is available"
                    }
                else:
                    return {
                        "status": "degraded",
                        "message": f"Service returned status {response.status}"
                    }

        except Exception as e:
            logger.warning(f"Echo Brain health check failed: {e}")
            return {
                "status": "offline",
                "message": "Echo Brain anime module is not available"
            }

    # ============= Fallback Methods =============

    def _get_default_scene_plan(self) -> Dict[str, Any]:
        """Fallback scene plan when Echo Brain is unavailable"""
        return {
            "shot_list": [
                {
                    "shot_number": 1,
                    "description": "Establishing shot",
                    "suggested_camera_angle": "wide",
                    "character_emotions": {},
                    "suggested_poses": [],
                    "duration_seconds": 3.0
                },
                {
                    "shot_number": 2,
                    "description": "Character focus",
                    "suggested_camera_angle": "medium",
                    "character_emotions": {},
                    "suggested_poses": [],
                    "duration_seconds": 4.0
                }
            ],
            "overall_mood": "neutral",
            "lighting_suggestions": "standard anime lighting",
            "style_keywords": ["anime", "clean", "detailed"],
            "narrative_arc": "standard progression"
        }

    def _get_default_prompt_refinement(self, raw_prompt: str) -> Dict[str, Any]:
        """Fallback prompt refinement"""
        return {
            "enhanced_prompt": f"{raw_prompt}, high quality, anime style, detailed",
            "style_keywords": ["anime", "detailed", "vibrant"],
            "negative_prompt": "low quality, blurry, distorted, ugly",
            "cinematic_terms": ["rule of thirds", "balanced composition"],
            "character_consistency_hints": ["maintain character design", "consistent features"]
        }

    def _get_default_feedback_response(self) -> Dict[str, Any]:
        """Fallback feedback response"""
        return {
            "learned_elements": ["Generation recorded"],
            "updated_confidence_scores": {"overall": 0.5},
            "recommendations_for_next": ["Continue with current settings"]
        }


# Singleton instance for easy import
echo_anime_client = EchoAnimeClient()


async def test_integration():
    """Test the Echo Brain anime integration"""
    async with EchoAnimeClient() as client:
        # Test health check
        health = await client.check_health()
        print(f"Health Status: {health}")

        # Test scene planning
        scene_plan = await client.plan_scene(
            session_id="test_session",
            scene_description="A dramatic confrontation between Kai and the dragon in a burning city",
            characters=["Kai", "Dragon"],
            style_references=["dark fantasy", "epic scale"],
            duration=15
        )
        print(f"Scene Plan: {json.dumps(scene_plan, indent=2)}")

        # Test prompt refinement
        refined = await client.refine_prompt(
            session_id="test_session",
            raw_prompt="Kai standing with sword",
            character_name="Kai",
            emotion="determined",
            camera_angle="medium"
        )
        print(f"Refined Prompt: {json.dumps(refined, indent=2)}")

        # Test feedback submission
        feedback = await client.submit_feedback(
            session_id="test_session",
            generation_id="gen_001",
            prompt_used="enhanced prompt here",
            quality_scores={
                "ssim": 0.85,
                "optical_flow": 0.72,
                "character_consistency": 0.90
            },
            user_feedback="Good composition but lighting could be darker"
        )
        print(f"Feedback Response: {json.dumps(feedback, indent=2)}")


if __name__ == "__main__":
    # Run integration test
    asyncio.run(test_integration())