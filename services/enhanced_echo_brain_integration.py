#!/usr/bin/env python3
"""
Enhanced Echo Brain Integration with Improved Error Handling and Fallbacks
Provides robust AI-powered content generation with graceful degradation
"""

import asyncio
import json
import logging
import httpx
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
from datetime import datetime

# Import enhanced error handling
from ..shared.error_handling import (
    EchoBrainError, RetryManager, CircuitBreaker,
    metrics_collector, echo_brain_circuit_breaker
)

logger = logging.getLogger(__name__)

@dataclass
class EchoBrainConfig:
    """Enhanced configuration for Echo Brain service."""
    base_url: str = "http://192.168.50.135:8309"
    model: str = "llama3.1:8b"
    temperature: float = 0.7
    max_tokens: int = 500
    timeout: int = 60
    enabled: bool = True
    fallback_enabled: bool = True
    retry_attempts: int = 3
    circuit_breaker_threshold: int = 5

class EnhancedEchoBrainService:
    """Enhanced Echo Brain service with robust error handling and fallbacks."""

    def __init__(self, config: EchoBrainConfig = None):
        self.config = config or EchoBrainConfig()
        self.circuit_breaker = echo_brain_circuit_breaker
        self.retry_manager = RetryManager()

    async def check_status(self) -> Dict[str, Any]:
        """Enhanced status check with detailed diagnostics."""
        if not self.config.enabled:
            return {
                "status": "disabled",
                "message": "Echo Brain integration is disabled",
                "fallback_available": self.config.fallback_enabled
            }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.config.base_url}/api/echo/health")

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "status": "available",
                        "message": "Echo Brain is operational",
                        "service_info": data,
                        "model": self.config.model,
                        "circuit_breaker_state": self.circuit_breaker.state,
                        "fallback_available": self.config.fallback_enabled
                    }
                else:
                    logger.warning(f"Echo Brain health check failed: HTTP {response.status_code}")
                    return await self._handle_service_unavailable("Health check failed", response.status_code)

        except Exception as e:
            logger.error(f"Echo Brain health check error: {e}")
            return await self._handle_service_unavailable(f"Health check error: {str(e)}")

    async def enhance_scene_description(self,
                                      scene_description: str,
                                      context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Enhanced scene description with robust error handling and fallbacks."""
        operation_id = f"scene_enhancement_{int(datetime.utcnow().timestamp())}"

        try:
            # Build enhancement prompt
            enhancement_prompt = await self._build_enhancement_prompt(scene_description, context)

            # Try AI enhancement with circuit breaker protection
            enhanced_result = await self.circuit_breaker.call(
                self._query_echo_brain, enhancement_prompt, operation_id
            )

            if enhanced_result and enhanced_result.get("success"):
                return {
                    "status": "enhanced",
                    "original_description": scene_description,
                    "enhanced_description": enhanced_result.get("response", ""),
                    "ai_used": True,
                    "model_info": enhanced_result.get("model_used", "unknown"),
                    "processing_time": enhanced_result.get("processing_time", 0),
                    "operation_id": operation_id,
                    "fallback_used": False
                }
            else:
                raise EchoBrainError("AI enhancement failed", correlation_id=operation_id)

        except Exception as e:
            logger.warning(f"Echo Brain enhancement failed: {e}")

            if self.config.fallback_enabled:
                return await self._fallback_scene_enhancement(scene_description, context, operation_id)
            else:
                raise EchoBrainError(
                    f"Scene enhancement failed and fallback is disabled: {str(e)}",
                    correlation_id=operation_id
                )

    async def generate_character_dialogue(self,
                                        characters: List[Dict[str, Any]],
                                        scene_context: str,
                                        emotion: str = "neutral") -> Dict[str, Any]:
        """Generate character dialogue with enhanced error handling."""
        operation_id = f"dialogue_gen_{int(datetime.utcnow().timestamp())}"

        try:
            dialogue_prompt = await self._build_dialogue_prompt(characters, scene_context, emotion)

            result = await self.circuit_breaker.call(
                self._query_echo_brain, dialogue_prompt, operation_id
            )

            if result and result.get("success"):
                dialogue_lines = self._parse_dialogue_response(result.get("response", ""))
                return {
                    "status": "success",
                    "dialogue": dialogue_lines,
                    "characters": [char.get("name", "Unknown") for char in characters],
                    "emotion": emotion,
                    "ai_used": True,
                    "model_info": result.get("model_used", "unknown"),
                    "operation_id": operation_id,
                    "fallback_used": False
                }
            else:
                raise EchoBrainError("Dialogue generation failed", correlation_id=operation_id)

        except Exception as e:
            logger.warning(f"Dialogue generation failed: {e}")

            if self.config.fallback_enabled:
                return await self._fallback_dialogue_generation(characters, scene_context, emotion, operation_id)
            else:
                raise EchoBrainError(
                    f"Dialogue generation failed and fallback is disabled: {str(e)}",
                    correlation_id=operation_id
                )

    async def suggest_scene_continuation(self,
                                       current_scenes: List[Dict[str, Any]],
                                       project_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Suggest scene continuations with enhanced error handling."""
        operation_id = f"scene_continuation_{int(datetime.utcnow().timestamp())}"

        try:
            continuation_prompt = await self._build_continuation_prompt(current_scenes, project_context)

            result = await self.circuit_breaker.call(
                self._query_echo_brain, continuation_prompt, operation_id
            )

            if result and result.get("success"):
                suggestions = self._parse_continuation_response(result.get("response", ""))
                return {
                    "status": "success",
                    "suggestions": suggestions,
                    "current_scene_count": len(current_scenes),
                    "ai_used": True,
                    "model_info": result.get("model_used", "unknown"),
                    "operation_id": operation_id,
                    "fallback_used": False
                }
            else:
                raise EchoBrainError("Scene continuation failed", correlation_id=operation_id)

        except Exception as e:
            logger.warning(f"Scene continuation failed: {e}")

            if self.config.fallback_enabled:
                return await self._fallback_scene_continuation(current_scenes, project_context, operation_id)
            else:
                raise EchoBrainError(
                    f"Scene continuation failed and fallback is disabled: {str(e)}",
                    correlation_id=operation_id
                )

    async def _query_echo_brain(self, prompt: str, operation_id: str) -> Dict[str, Any]:
        """Query Echo Brain with retry logic and proper error handling."""
        async def _make_request():
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                payload = {
                    "query": prompt,
                    "conversation_id": f"anime_production_{operation_id}",
                    "model": self.config.model,
                    "temperature": self.config.temperature,
                    "max_tokens": self.config.max_tokens
                }

                response = await client.post(
                    f"{self.config.base_url}/api/echo/query",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "response": data.get("response", ""),
                        "model_used": data.get("model_used", "unknown"),
                        "processing_time": data.get("processing_time", 0)
                    }
                else:
                    raise EchoBrainError(
                        f"Echo Brain query failed: HTTP {response.status_code}",
                        correlation_id=operation_id
                    )

        return await self.retry_manager.retry_with_backoff(
            _make_request,
            max_retries=self.config.retry_attempts,
            exceptions=(httpx.RequestError, EchoBrainError)
        )

    async def _handle_service_unavailable(self, reason: str, status_code: int = None) -> Dict[str, Any]:
        """Handle service unavailable scenarios."""
        return {
            "status": "unavailable",
            "message": f"Echo Brain service unavailable: {reason}",
            "status_code": status_code,
            "fallback_available": self.config.fallback_enabled,
            "circuit_breaker_state": self.circuit_breaker.state,
            "retry_recommended": status_code != 404 if status_code else True
        }

    async def _build_enhancement_prompt(self, scene_description: str, context: Dict[str, Any] = None) -> str:
        """Build comprehensive enhancement prompt."""
        project_info = context.get("project", {}) if context else {}

        return f"""Please enhance this anime scene description for better visual generation:

Original Scene: {scene_description}

Project Context:
- Title: {project_info.get('name', 'Unknown Project')}
- Genre: {project_info.get('genre', 'Anime')}
- Style: {project_info.get('style', 'Standard anime style')}

Enhancement Requirements:
1. Add specific visual details (lighting, camera angles, composition)
2. Include character positioning and expressions
3. Describe environmental atmosphere and mood
4. Add technical details for anime generation (quality tags, style specifications)
5. Ensure description is optimized for AI image generation

Please provide the enhanced description in a clear, detailed format suitable for ComfyUI anime generation."""

    async def _build_dialogue_prompt(self, characters: List[Dict[str, Any]], scene_context: str, emotion: str) -> str:
        """Build dialogue generation prompt."""
        char_descriptions = []
        for char in characters:
            char_descriptions.append(f"- {char.get('name', 'Unknown')}: {char.get('personality', 'Not specified')}")

        return f"""Generate natural anime character dialogue for this scene:

Characters:
{chr(10).join(char_descriptions)}

Scene Context: {scene_context}
Emotion/Tone: {emotion}

Requirements:
1. Keep dialogue true to each character's personality
2. Make it appropriate for anime style
3. Include emotional context and delivery notes
4. Format as character_name: "dialogue" (delivery_note)

Generate 2-3 lines of dialogue that advance the scene naturally."""

    async def _build_continuation_prompt(self, current_scenes: List[Dict[str, Any]], project_context: Dict[str, Any] = None) -> str:
        """Build scene continuation prompt."""
        scene_summaries = []
        for i, scene in enumerate(current_scenes[-3:]):  # Last 3 scenes for context
            scene_summaries.append(f"Scene {i+1}: {scene.get('title', 'Untitled')} - {scene.get('description', '')}")

        project_info = project_context or {}

        return f"""Suggest 2-3 natural continuation scenes for this anime project:

Project: {project_info.get('name', 'Anime Project')}
Genre: {project_info.get('genre', 'General')}

Recent Scenes:
{chr(10).join(scene_summaries)}

Requirements:
1. Suggest logical story progression
2. Maintain character consistency
3. Include scene titles and brief descriptions
4. Consider pacing and narrative flow

Format each suggestion as:
Title: [Scene Title]
Description: [Brief scene description]
Purpose: [How it advances the story]"""

    async def _fallback_scene_enhancement(self, scene_description: str, context: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        """Provide fallback scene enhancement when AI is unavailable."""
        project_info = context.get("project", {}) if context else {}
        genre = project_info.get("genre", "anime").lower()

        # Rule-based enhancement based on genre and keywords
        enhanced_description = scene_description

        # Add quality tags
        enhanced_description += ", masterpiece, best quality, highly detailed"

        # Add style tags based on genre
        if "cyberpunk" in genre or "sci-fi" in genre:
            enhanced_description += ", neon lights, futuristic cityscape, cyberpunk aesthetic"
        elif "fantasy" in genre:
            enhanced_description += ", magical atmosphere, fantasy setting, ethereal lighting"
        else:
            enhanced_description += ", anime style, vibrant colors, dynamic composition"

        # Add general anime tags
        enhanced_description += ", detailed background, professional artwork, 4k resolution"

        logger.info(f"Applied rule-based scene enhancement for operation {operation_id}")

        return {
            "status": "enhanced",
            "original_description": scene_description,
            "enhanced_description": enhanced_description,
            "ai_used": False,
            "enhancement_method": "rule-based",
            "operation_id": operation_id,
            "fallback_used": True,
            "fallback_reason": "AI service unavailable"
        }

    async def _fallback_dialogue_generation(self, characters: List[Dict[str, Any]], scene_context: str, emotion: str, operation_id: str) -> Dict[str, Any]:
        """Provide fallback dialogue generation."""
        dialogue_lines = []

        for i, char in enumerate(characters):
            char_name = char.get("name", f"Character_{i+1}")
            personality = char.get("personality", "")

            # Simple template-based dialogue
            if emotion == "dramatic":
                dialogue_lines.append(f'{char_name}: "This changes everything..." (with intense emotion)')
            elif emotion == "happy":
                dialogue_lines.append(f'{char_name}: "I can\'t believe it worked!" (with excitement)')
            elif emotion == "sad":
                dialogue_lines.append(f'{char_name}: "I never thought it would end this way..." (with melancholy)')
            else:
                dialogue_lines.append(f'{char_name}: "Let\'s see what happens next." (thoughtfully)')

        logger.info(f"Applied template-based dialogue generation for operation {operation_id}")

        return {
            "status": "success",
            "dialogue": dialogue_lines,
            "characters": [char.get("name", "Unknown") for char in characters],
            "emotion": emotion,
            "ai_used": False,
            "generation_method": "template-based",
            "operation_id": operation_id,
            "fallback_used": True,
            "fallback_reason": "AI service unavailable"
        }

    async def _fallback_scene_continuation(self, current_scenes: List[Dict[str, Any]], project_context: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        """Provide fallback scene continuation suggestions."""
        scene_count = len(current_scenes)
        suggestions = []

        # Generic continuation suggestions based on common anime patterns
        suggestions.append({
            "title": f"Scene {scene_count + 1}: Character Development",
            "description": "A quieter moment focusing on character relationships and internal growth",
            "purpose": "Develops character depth and emotional connection"
        })

        suggestions.append({
            "title": f"Scene {scene_count + 2}: Rising Action",
            "description": "Tension builds as new challenges or conflicts emerge",
            "purpose": "Advances main plot and increases dramatic tension"
        })

        suggestions.append({
            "title": f"Scene {scene_count + 3}: Revelation",
            "description": "Important information is revealed that changes the story direction",
            "purpose": "Provides plot twist or crucial story development"
        })

        logger.info(f"Applied template-based scene continuation for operation {operation_id}")

        return {
            "status": "success",
            "suggestions": suggestions,
            "current_scene_count": scene_count,
            "ai_used": False,
            "generation_method": "template-based",
            "operation_id": operation_id,
            "fallback_used": True,
            "fallback_reason": "AI service unavailable"
        }

    def _parse_dialogue_response(self, response: str) -> List[str]:
        """Parse dialogue from AI response."""
        lines = []
        for line in response.split('\n'):
            line = line.strip()
            if ':' in line and ('"' in line or "'" in line):
                lines.append(line)
        return lines if lines else [response.strip()]

    def _parse_continuation_response(self, response: str) -> List[Dict[str, str]]:
        """Parse scene continuation suggestions from AI response."""
        suggestions = []
        current_suggestion = {}

        for line in response.split('\n'):
            line = line.strip()
            if line.startswith('Title:'):
                if current_suggestion:
                    suggestions.append(current_suggestion)
                current_suggestion = {"title": line[6:].strip()}
            elif line.startswith('Description:') and current_suggestion:
                current_suggestion["description"] = line[12:].strip()
            elif line.startswith('Purpose:') and current_suggestion:
                current_suggestion["purpose"] = line[8:].strip()

        if current_suggestion:
            suggestions.append(current_suggestion)

        return suggestions if suggestions else [{"title": "Continue Story", "description": response.strip(), "purpose": "Advance narrative"}]

# Global enhanced service instance
enhanced_echo_brain_service = EnhancedEchoBrainService()