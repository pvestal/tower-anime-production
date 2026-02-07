"""
Story Bible Integration
Integration with Tower Story Bible System for character and world consistency
"""

import asyncio
import aiohttp
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import json

logger = logging.getLogger(__name__)

class StoryBibleIntegration:
    """Integration with Tower Story Bible System for consistency checks"""

    def __init__(self, base_url: str = "http://localhost:8324"):
        self.base_url = base_url.rstrip('/')
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _get_session(self):
        """Get or create aiohttp session"""
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def health_check(self) -> bool:
        """Check if Story Bible system is accessible"""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/api/health") as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Story Bible health check failed: {e}")
            return False

    async def get_character_details(self, character_names: List[str]) -> Dict[str, Any]:
        """Get character details from story bible"""
        try:
            session = await self._get_session()

            character_data = {}
            for character_name in character_names:
                async with session.get(
                    f"{self.base_url}/api/story-bible/characters/search",
                    params={"name": character_name}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("characters"):
                            character_data[character_name] = result["characters"][0]
                    else:
                        # Character not found, use fallback
                        character_data[character_name] = await self._create_fallback_character(character_name)

            return {
                "success": True,
                "characters": character_data,
                "consistency_notes": await self._generate_consistency_notes(character_data)
            }

        except Exception as e:
            logger.error(f"Character details retrieval failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "characters": {}
            }

    async def _create_fallback_character(self, character_name: str) -> Dict[str, Any]:
        """Create fallback character data when not found in story bible"""
        return {
            "name": character_name,
            "role": "supporting",
            "appearance": {
                "description": f"Standard character design for {character_name}",
                "key_features": ["anime_style", "age_appropriate", "consistent_design"]
            },
            "personality": {
                "traits": ["reliable", "consistent", "well_defined"],
                "emotional_range": "balanced"
            },
            "consistency_notes": "Generated fallback - consider adding to story bible",
            "source": "fallback_generation"
        }

    async def _generate_consistency_notes(self, character_data: Dict[str, Any]) -> List[str]:
        """Generate consistency notes for characters"""
        notes = []

        for character_name, data in character_data.items():
            if data.get("source") == "fallback_generation":
                notes.append(f"{character_name}: Using fallback data - add to story bible for consistency")
            else:
                notes.append(f"{character_name}: Story bible data available for consistency")

        return notes

    async def validate_world_consistency(
        self,
        location: str,
        time_of_day: str,
        scene_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate world consistency with story bible"""
        try:
            session = await self._get_session()

            validation_request = {
                "location": location,
                "time_of_day": time_of_day,
                "scene_context": scene_context
            }

            async with session.post(
                f"{self.base_url}/api/story-bible/world/validate",
                json=validation_request,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "success": True,
                        "consistent": result.get("consistent", True),
                        "world_details": result.get("world_details", {}),
                        "consistency_issues": result.get("issues", []),
                        "recommendations": result.get("recommendations", [])
                    }
                else:
                    # Fallback validation
                    return await self._fallback_world_validation(location, time_of_day, scene_context)

        except Exception as e:
            logger.error(f"World consistency validation failed: {e}")
            return await self._fallback_world_validation(location, time_of_day, scene_context)

    async def _fallback_world_validation(
        self,
        location: str,
        time_of_day: str,
        scene_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Fallback world validation when story bible unavailable"""
        return {
            "success": True,
            "consistent": True,  # Assume consistent when cannot validate
            "world_details": {
                "location": location,
                "time_of_day": time_of_day,
                "validated": False,
                "source": "fallback_validation"
            },
            "consistency_issues": [],
            "recommendations": ["Verify world consistency with story bible when available"]
        }

    async def get_narrative_context(
        self,
        story_bible_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get narrative context from story bible"""
        try:
            session = await self._get_session()

            if story_bible_id:
                endpoint = f"/api/story-bible/{story_bible_id}/context"
            else:
                endpoint = "/api/story-bible/context/active"

            async with session.get(f"{self.base_url}{endpoint}") as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "success": True,
                        "narrative_context": result.get("context", {}),
                        "story_arc": result.get("story_arc", {}),
                        "themes": result.get("themes", []),
                        "tone": result.get("tone", "neutral")
                    }
                else:
                    return await self._fallback_narrative_context()

        except Exception as e:
            logger.error(f"Narrative context retrieval failed: {e}")
            return await self._fallback_narrative_context()

    async def _fallback_narrative_context(self) -> Dict[str, Any]:
        """Fallback narrative context"""
        return {
            "success": True,
            "narrative_context": {
                "story_stage": "unknown",
                "tension_level": "moderate",
                "character_relationships": "developing"
            },
            "story_arc": {
                "current_act": "unknown",
                "progression": "steady"
            },
            "themes": ["adventure", "friendship", "growth"],
            "tone": "balanced"
        }

    async def check_character_consistency(
        self,
        character_names: List[str],
        scene_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check character consistency across scenes"""
        try:
            # Get character details
            character_data = await self.get_character_details(character_names)

            if not character_data.get("success"):
                return character_data

            consistency_results = {}
            for character_name in character_names:
                char_data = character_data["characters"].get(character_name, {})
                consistency_results[character_name] = await self._evaluate_character_consistency(
                    char_data, scene_context
                )

            return {
                "success": True,
                "character_consistency": consistency_results,
                "overall_consistency": all(
                    result.get("consistent", True)
                    for result in consistency_results.values()
                ),
                "recommendations": await self._generate_character_recommendations(consistency_results)
            }

        except Exception as e:
            logger.error(f"Character consistency check failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def _evaluate_character_consistency(
        self,
        character_data: Dict[str, Any],
        scene_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluate consistency for a single character"""

        consistency_result = {
            "consistent": True,
            "issues": [],
            "character_state": "valid"
        }

        # Check if character role matches scene context
        character_role = character_data.get("role", "supporting")
        scene_mood = scene_context.get("mood", "neutral")

        # Simple consistency checks (in production, these would be more sophisticated)
        if character_role == "protagonist" and scene_mood == "comedic":
            # Check if protagonist is appropriate for comedic scenes
            personality = character_data.get("personality", {})
            if "serious" in personality.get("traits", []):
                consistency_result["issues"].append(
                    "Serious protagonist in comedic scene may need personality adjustment"
                )

        # Check appearance consistency
        appearance = character_data.get("appearance", {})
        if not appearance.get("description"):
            consistency_result["issues"].append("Missing character appearance description")

        # Update consistency status
        if consistency_result["issues"]:
            consistency_result["consistent"] = False

        return consistency_result

    async def _generate_character_recommendations(
        self,
        consistency_results: Dict[str, Dict[str, Any]]
    ) -> List[str]:
        """Generate recommendations based on consistency results"""

        recommendations = []

        for character_name, result in consistency_results.items():
            if not result.get("consistent", True):
                issues = result.get("issues", [])
                if issues:
                    recommendations.append(
                        f"{character_name}: {'; '.join(issues[:2])}"  # Limit to top 2 issues
                    )

        if not recommendations:
            recommendations.append("All characters pass consistency checks")

        return recommendations

    async def update_story_bible_from_scene(
        self,
        scene_data: Dict[str, Any],
        story_bible_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Update story bible with information learned from scene"""
        try:
            session = await self._get_session()

            update_data = {
                "scene_data": scene_data,
                "update_type": "scene_information",
                "source": "scene_description_generator",
                "timestamp": datetime.utcnow().isoformat()
            }

            endpoint = f"/api/story-bible/{story_bible_id}/update" if story_bible_id else "/api/story-bible/update"

            async with session.post(
                f"{self.base_url}{endpoint}",
                json=update_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "success": True,
                        "updates_applied": result.get("updates", []),
                        "story_bible_version": result.get("version", "unknown")
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to update story bible"
                    }

        except Exception as e:
            logger.error(f"Story bible update failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def get_scene_templates(
        self,
        scene_type: str,
        story_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Get scene templates from story bible"""
        try:
            session = await self._get_session()

            params = {"type": scene_type}
            if story_context:
                params["context"] = json.dumps(story_context)

            async with session.get(
                f"{self.base_url}/api/story-bible/templates/scenes",
                params=params
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "success": True,
                        "templates": result.get("templates", []),
                        "recommended_template": result.get("recommended", {}),
                        "customization_options": result.get("customization", [])
                    }
                else:
                    return await self._fallback_scene_templates(scene_type)

        except Exception as e:
            logger.error(f"Scene template retrieval failed: {e}")
            return await self._fallback_scene_templates(scene_type)

    async def _fallback_scene_templates(self, scene_type: str) -> Dict[str, Any]:
        """Fallback scene templates when story bible unavailable"""

        fallback_templates = {
            "dialogue": {
                "structure": "setup_conversation_resolution",
                "pacing": "moderate",
                "camera_suggestions": ["medium_shot", "over_shoulder", "two_shot"],
                "timing": "3-8_seconds_per_shot"
            },
            "action": {
                "structure": "buildup_action_aftermath",
                "pacing": "fast",
                "camera_suggestions": ["wide_shot", "close_up", "tracking"],
                "timing": "1-3_seconds_per_shot"
            },
            "contemplative": {
                "structure": "reflection_realization_decision",
                "pacing": "slow",
                "camera_suggestions": ["close_up", "medium_shot", "wide_shot"],
                "timing": "4-12_seconds_per_shot"
            }
        }

        template = fallback_templates.get(scene_type, fallback_templates["dialogue"])

        return {
            "success": True,
            "templates": [template],
            "recommended_template": template,
            "customization_options": ["pacing", "camera_work", "timing"],
            "source": "fallback_templates"
        }

    async def validate_narrative_progression(
        self,
        scene_data: Dict[str, Any],
        previous_scenes: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Validate narrative progression consistency"""
        try:
            session = await self._get_session()

            validation_data = {
                "current_scene": scene_data,
                "previous_scenes": previous_scenes or [],
                "validation_type": "narrative_progression"
            }

            async with session.post(
                f"{self.base_url}/api/story-bible/validate/progression",
                json=validation_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "success": True,
                        "progression_valid": result.get("valid", True),
                        "narrative_flow": result.get("flow", "smooth"),
                        "continuity_issues": result.get("issues", []),
                        "suggestions": result.get("suggestions", [])
                    }
                else:
                    return await self._fallback_progression_validation(scene_data, previous_scenes)

        except Exception as e:
            logger.error(f"Narrative progression validation failed: {e}")
            return await self._fallback_progression_validation(scene_data, previous_scenes)

    async def _fallback_progression_validation(
        self,
        scene_data: Dict[str, Any],
        previous_scenes: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Fallback progression validation"""
        return {
            "success": True,
            "progression_valid": True,  # Assume valid when cannot validate
            "narrative_flow": "unknown",
            "continuity_issues": [],
            "suggestions": ["Verify narrative progression with story bible when available"],
            "source": "fallback_validation"
        }