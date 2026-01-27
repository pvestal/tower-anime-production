"""
Echo Brain AI integration service for Tower Anime Production API
Handles AI-driven creative suggestions, dialogue generation, and story development
"""

import os
import json
import logging
import asyncio
import aiohttp
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Echo Brain configuration - Use domain-aware configuration
from ..core.config import ECHO_BRAIN_URL as DEFAULT_ECHO_URL
ECHO_SERVICE_URL = os.getenv('ECHO_SERVICE_URL', DEFAULT_ECHO_URL)


class EchoBrainService:
    """Service for Echo Brain AI creative assistance"""

    def __init__(self):
        self.echo_url = ECHO_SERVICE_URL
        self.enabled = True
        self.model = "gpt-3.5-turbo"
        self.temperature = 0.7

    def check_status(self) -> Dict[str, Any]:
        """Check if Echo Brain service is available"""
        return {
            "available": True,  # For demo purposes
            "model": self.model,
            "temperature": self.temperature,
            "enabled": self.enabled
        }

    async def suggest_scene_details(
        self,
        context: Dict[str, Any],
        current_prompt: str = ""
    ) -> Dict[str, Any]:
        """Generate scene suggestions based on project context"""
        try:
            logger.info(f"Generating scene suggestions for project: {context.get('project_name')}")

            # Build comprehensive context for AI
            project_context = self._build_project_context(context)

            # Mock AI suggestions for now - replace with actual Echo Brain API call
            suggestions = {
                "scene_variations": [
                    {
                        "title": "Character Introduction Scene",
                        "description": f"Introduce {context.get('characters', [{}])[0].get('name', 'protagonist')} in their natural environment",
                        "mood": "establishing",
                        "camera_angles": ["medium shot", "close-up"],
                        "duration": "3-5 seconds"
                    },
                    {
                        "title": "Dialogue Exchange",
                        "description": "Character interaction showing personality dynamics",
                        "mood": "conversational",
                        "camera_angles": ["shot-reverse-shot", "wide shot"],
                        "duration": "5-8 seconds"
                    },
                    {
                        "title": "Emotional Moment",
                        "description": "Character expressing key emotion relevant to story",
                        "mood": "dramatic",
                        "camera_angles": ["close-up", "extreme close-up"],
                        "duration": "3-4 seconds"
                    }
                ],
                "character_actions": self._suggest_character_actions(context),
                "environment_details": self._suggest_environments(context),
                "technical_suggestions": {
                    "lighting": "dramatic anime lighting with soft shadows",
                    "style": "high-quality anime art style",
                    "composition": "rule of thirds, dynamic framing"
                }
            }

            return suggestions

        except Exception as e:
            logger.error(f"Scene suggestion generation failed: {e}")
            return {"error": str(e), "suggestions": []}

    async def generate_dialogue(
        self,
        character: Dict[str, Any],
        scene_context: str,
        emotion: str = "neutral"
    ) -> Dict[str, Any]:
        """Generate dialogue for a character in specific context"""
        try:
            logger.info(f"Generating dialogue for character: {character.get('name')}")

            # Build character profile
            character_profile = {
                "name": character.get("name", "Character"),
                "personality": character.get("personality", ""),
                "background": character.get("background", ""),
                "traits": character.get("traits", [])
            }

            # Mock dialogue generation - replace with actual AI call
            dialogue_options = [
                {
                    "text": f"This feels like the right moment to act.",
                    "emotion": emotion,
                    "delivery": "confident",
                    "context_fit": 0.85
                },
                {
                    "text": f"I'm not sure about this path we're taking.",
                    "emotion": "uncertain" if emotion == "neutral" else emotion,
                    "delivery": "hesitant",
                    "context_fit": 0.78
                },
                {
                    "text": f"Whatever happens next, we face it together.",
                    "emotion": "determined",
                    "delivery": "resolute",
                    "context_fit": 0.92
                }
            ]

            return {
                "character_name": character["name"],
                "dialogue_options": dialogue_options,
                "character_context": character_profile,
                "scene_context": scene_context
            }

        except Exception as e:
            logger.error(f"Dialogue generation failed: {e}")
            return {"error": str(e), "dialogue_options": []}

    async def continue_episode(
        self,
        episode_context: Dict[str, Any],
        direction: str = "continue"
    ) -> Dict[str, Any]:
        """Suggest episode continuation options"""
        try:
            logger.info(f"Generating episode continuation for: {episode_context.get('title')}")

            # Analyze existing scenes
            scenes = episode_context.get("scenes", [])
            scene_count = len(scenes)

            # Mock continuation suggestions
            continuations = [
                {
                    "type": "plot_advancement",
                    "title": "Conflict Escalation",
                    "description": "Introduce a new challenge that tests the characters",
                    "suggested_scenes": [
                        "Character realizes the stakes are higher",
                        "Confrontation with opposing force",
                        "Moment of character growth"
                    ],
                    "narrative_impact": "high"
                },
                {
                    "type": "character_development",
                    "title": "Internal Journey",
                    "description": "Focus on character's emotional arc",
                    "suggested_scenes": [
                        "Quiet reflection moment",
                        "Memory or flashback",
                        "Decision point"
                    ],
                    "narrative_impact": "medium"
                },
                {
                    "type": "world_building",
                    "title": "Environment Exploration",
                    "description": "Expand the story world and context",
                    "suggested_scenes": [
                        "New location reveal",
                        "Cultural or world detail",
                        "Atmospheric moment"
                    ],
                    "narrative_impact": "medium"
                }
            ]

            return {
                "episode_title": episode_context.get("title"),
                "current_scene_count": scene_count,
                "continuation_options": continuations,
                "narrative_analysis": {
                    "pacing": "building" if scene_count < 5 else "climactic",
                    "character_arc_stage": "development",
                    "tension_level": "moderate"
                }
            }

        except Exception as e:
            logger.error(f"Episode continuation failed: {e}")
            return {"error": str(e), "continuations": []}

    async def analyze_storyline(
        self,
        project_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze overall project storyline and suggest improvements"""
        try:
            logger.info(f"Analyzing storyline for project: {project_data.get('name')}")

            # Mock storyline analysis
            analysis = {
                "story_structure": {
                    "act_1": "Character introduction and world setup",
                    "act_2": "Conflict development and character growth",
                    "act_3": "Climax and resolution"
                },
                "character_arcs": [
                    {
                        "character": "Protagonist",
                        "arc_type": "hero's journey",
                        "completion": 0.6,
                        "next_milestone": "face the shadow"
                    }
                ],
                "themes": [
                    "personal growth",
                    "friendship",
                    "overcoming challenges"
                ],
                "suggestions": [
                    "Consider adding a subplot for secondary character",
                    "Strengthen the midpoint turning point",
                    "Add foreshadowing for the climax"
                ]
            }

            return analysis

        except Exception as e:
            logger.error(f"Storyline analysis failed: {e}")
            return {"error": str(e), "analysis": {}}

    async def brainstorm_project_ideas(
        self,
        project_id: int,
        brainstorm_type: str = "general"
    ) -> Dict[str, Any]:
        """Generate creative brainstorming suggestions for project"""
        try:
            logger.info(f"Brainstorming ideas for project {project_id}, type: {brainstorm_type}")

            brainstorm_categories = {
                "characters": [
                    "Mysterious mentor with hidden past",
                    "Rival who becomes unexpected ally",
                    "Comic relief with surprising depth"
                ],
                "plot_twists": [
                    "The enemy was trying to protect something",
                    "The quest was a test all along",
                    "The power was within them from the start"
                ],
                "world_building": [
                    "Hidden society within modern world",
                    "Ancient technology in fantasy setting",
                    "Parallel dimensions bleeding through"
                ],
                "themes": [
                    "The cost of power",
                    "Finding family in unexpected places",
                    "Courage in the face of uncertainty"
                ]
            }

            return {
                "brainstorm_type": brainstorm_type,
                "ideas": brainstorm_categories,
                "creative_prompts": [
                    "What if your protagonist had to choose between saving one person they love or many strangers?",
                    "What if the main conflict could be solved through understanding rather than fighting?",
                    "What if the story took place in a completely different time period?"
                ]
            }

        except Exception as e:
            logger.error(f"Brainstorming failed: {e}")
            return {"error": str(e), "ideas": {}}

    def _build_project_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Build comprehensive project context for AI"""
        return {
            "project": {
                "name": context.get("project_name", ""),
                "genre": context.get("genre", "anime"),
                "style": context.get("style", "anime")
            },
            "characters": [
                {
                    "name": char.get("name", ""),
                    "personality": char.get("personality", ""),
                    "traits": char.get("traits", [])
                }
                for char in context.get("characters", [])
            ],
            "world": {
                "setting": context.get("setting", "modern"),
                "tone": context.get("tone", "dramatic")
            }
        }

    def _suggest_character_actions(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Suggest character-specific actions for scenes"""
        characters = context.get("characters", [])
        actions = []

        for char in characters[:3]:  # Limit to first 3 characters
            char_name = char.get("name", "Character")
            personality = char.get("personality", "")

            if "confident" in personality.lower():
                actions.append({
                    "character": char_name,
                    "action": "takes decisive action",
                    "motivation": "natural leadership tendency"
                })
            elif "shy" in personality.lower():
                actions.append({
                    "character": char_name,
                    "action": "hesitates before speaking",
                    "motivation": "cautious nature"
                })
            else:
                actions.append({
                    "character": char_name,
                    "action": "observes situation carefully",
                    "motivation": "analytical approach"
                })

        return actions

    def _suggest_environments(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Suggest environment details for scenes"""
        return [
            {
                "setting": "Urban rooftop at sunset",
                "mood": "contemplative",
                "lighting": "golden hour, dramatic shadows",
                "details": "city skyline, gentle breeze"
            },
            {
                "setting": "Cozy indoor cafe",
                "mood": "intimate",
                "lighting": "warm, soft lighting",
                "details": "steam from coffee, background chatter"
            },
            {
                "setting": "School hallway",
                "mood": "everyday life",
                "lighting": "fluorescent, institutional",
                "details": "lockers, students in background"
            }
        ]

    async def store_suggestion(
        self,
        db: Session,
        project_id: Optional[int] = None,
        episode_id: Optional[int] = None,
        character_id: Optional[int] = None,
        scene_id: Optional[int] = None,
        request_type: str = "general",
        request_data: Dict[str, Any] = None,
        response_data: Dict[str, Any] = None
    ) -> int:
        """Store suggestion in database for future reference"""
        try:
            from ..models import EchoBrainSuggestion

            suggestion = EchoBrainSuggestion(
                project_id=project_id,
                episode_id=episode_id,
                character_id=character_id,
                scene_id=scene_id,
                request_type=request_type,
                request_data=request_data or {},
                response_data=response_data or {}
            )

            db.add(suggestion)
            db.commit()
            db.refresh(suggestion)

            return suggestion.id

        except Exception as e:
            logger.error(f"Failed to store suggestion: {e}")
            db.rollback()
            return -1


# Global service instance
echo_brain_service = EchoBrainService()