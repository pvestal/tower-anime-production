#!/usr/bin/env python3
"""
Echo Brain Client Service
Provides async wrapper for Echo Brain API integration
"""

import asyncio
import json
import logging
import httpx
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

logger = logging.getLogger(__name__)

class EchoBrainClient:
    """Async client for Echo Brain API integration"""

    def __init__(self, base_url: str = "http://192.168.50.135:8309"):
        self.base_url = base_url.rstrip("/")
        self.session: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.aclose()

    async def _ensure_session(self):
        """Ensure HTTP session is available"""
        if not self.session:
            self.session = httpx.AsyncClient(timeout=30.0)

    async def health_check(self) -> bool:
        """Check if Echo Brain service is available"""
        try:
            await self._ensure_session()
            response = await self.session.get(f"{self.base_url}/api/echo/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Echo Brain health check failed: {e}")
            return False

    async def query(self,
                   query: str,
                   model: str = "tinyllama:latest",
                   conversation_id: Optional[str] = None,
                   context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Send query to Echo Brain and get response

        Args:
            query: The query text
            model: Model to use for processing
            conversation_id: Optional conversation ID for context
            context: Additional context data

        Returns:
            Response from Echo Brain
        """
        try:
            await self._ensure_session()

            payload = {
                "query": query,
                "model": model
            }

            if conversation_id:
                payload["conversation_id"] = conversation_id

            if context:
                payload["context"] = context

            logger.info(f"Sending query to Echo Brain: {query[:100]}...")

            response = await self.session.post(
                f"{self.base_url}/api/echo/query",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 200:
                result = response.json()
                logger.info("Echo Brain query successful")
                return result
            else:
                error_msg = f"Echo Brain query failed: {response.status_code} {response.text}"
                logger.error(error_msg)
                return {"error": error_msg, "status_code": response.status_code}

        except Exception as e:
            error_msg = f"Echo Brain query exception: {e}"
            logger.error(error_msg)
            return {"error": error_msg}

    async def generate_workflow(self,
                               prompt: str,
                               workflow_type: str = "image",
                               parameters: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Generate ComfyUI workflow using Echo Brain intelligence

        Args:
            prompt: Generation prompt
            workflow_type: Type of workflow (image, video, etc.)
            parameters: Additional parameters

        Returns:
            Generated workflow or error
        """
        context = {
            "task": "comfyui_workflow_generation",
            "workflow_type": workflow_type,
            "parameters": parameters or {}
        }

        query = f"""Generate a ComfyUI workflow for the following request:

Prompt: {prompt}
Type: {workflow_type}
Parameters: {json.dumps(parameters or {}, indent=2)}

Return a complete ComfyUI workflow JSON that can be executed directly.
Focus on:
- Proper node connections
- Appropriate model selection
- Optimal parameters for quality
- Efficient processing pipeline

Workflow JSON:"""

        return await self.query(
            query=query,
            model="tinyllama:latest",  # Fast model for workflow generation
            context=context
        )

    async def classify_intent(self, user_input: str) -> Dict[str, Any]:
        """
        Classify user intent for routing requests

        Args:
            user_input: User's input text

        Returns:
            Intent classification results
        """
        query = f"""Classify the intent of this user input for an anime production system:

Input: "{user_input}"

Classify into one of these categories:
1. image_generation - User wants to generate character images or scenes
2. video_generation - User wants to create animated videos
3. character_creation - User wants to design new characters
4. story_development - User wants to work on storylines
5. workflow_help - User needs help with the system
6. project_management - User wants to manage projects/files
7. quality_improvement - User wants to enhance existing content
8. other - None of the above

Respond with JSON format:
{{
    "intent": "category_name",
    "confidence": 0.95,
    "parameters": {{
        "extracted_prompt": "cleaned prompt if applicable",
        "workflow_type": "image/video/etc",
        "urgency": "low/medium/high"
    }},
    "suggestions": ["suggestion1", "suggestion2"]
}}"""

        return await self.query(
            query=query,
            model="tinyllama:latest",  # Ultra-fast model for intent classification
            context={"task": "intent_classification"}
        )

    async def get_suggestions(self,
                             context: Dict[str, Any],
                             user_history: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Get contextual suggestions based on current state

        Args:
            context: Current context (project, workflow, etc.)
            user_history: Optional user history for personalization

        Returns:
            Contextual suggestions
        """
        query = f"""Based on the current context, provide helpful suggestions for the user:

Context: {json.dumps(context, indent=2)}

User History: {json.dumps(user_history[-5:] if user_history else [], indent=2)}

Provide 3-5 actionable suggestions that would help the user:
1. Continue their current workflow
2. Improve their results
3. Explore new features
4. Optimize their process

Format as JSON:
{{
    "suggestions": [
        {{
            "title": "Suggestion Title",
            "description": "Detailed description",
            "action": "specific_action",
            "priority": "high/medium/low"
        }}
    ],
    "next_steps": ["step1", "step2"],
    "tips": ["tip1", "tip2"]
}}"""

        return await self.query(
            query=query,
            model="tinyllama:latest",  # Fast model for suggestions
            context={"task": "suggestion_generation"}
        )

    async def enhance_prompt(self,
                           original_prompt: str,
                           style_preferences: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Enhance user prompt for better generation results

        Args:
            original_prompt: User's original prompt
            style_preferences: Style preferences and parameters

        Returns:
            Enhanced prompt and suggestions
        """
        query = f"""Enhance this anime generation prompt for better results:

Original: "{original_prompt}"

Style Preferences: {json.dumps(style_preferences or {}, indent=2)}

Provide:
1. Enhanced version with better descriptive language
2. Technical parameters for optimal generation
3. Alternative variations to try
4. Quality improvement suggestions

Format as JSON:
{{
    "enhanced_prompt": "improved prompt text",
    "technical_params": {{
        "steps": 30,
        "cfg_scale": 7.5,
        "resolution": "1024x1024"
    }},
    "variations": ["variation1", "variation2"],
    "quality_tips": ["tip1", "tip2"]
}}"""

        return await self.query(
            query=query,
            model="tinyllama:latest",  # Fast model for prompt enhancement
            context={"task": "prompt_enhancement"}
        )

    async def analyze_generation_result(self,
                                      image_path: str,
                                      original_prompt: str) -> Dict[str, Any]:
        """
        Analyze generation results and provide feedback

        Args:
            image_path: Path to generated image
            original_prompt: Original generation prompt

        Returns:
            Analysis and improvement suggestions
        """
        # Note: This would need image analysis capabilities in Echo Brain
        # For now, provide text-based analysis

        query = f"""Analyze this anime generation result:

Original Prompt: "{original_prompt}"
Generated Image: {image_path}

Based on the prompt, provide analysis of likely results and suggestions:

1. Quality assessment based on prompt complexity
2. Suggestions for improvement
3. Alternative approaches
4. Technical adjustments

Format as JSON:
{{
    "quality_score": 8.5,
    "assessment": "detailed analysis",
    "improvements": ["suggestion1", "suggestion2"],
    "technical_adjustments": {{
        "steps": "increase to 40",
        "cfg_scale": "reduce to 6.0"
    }}
}}"""

        return await self.query(
            query=query,
            model="tinyllama:latest",  # Fast model for analysis
            context={"task": "result_analysis"}
        )

# Global client instance
echo_client = EchoBrainClient()

# Convenience functions for direct use
async def echo_query(query: str, **kwargs) -> Dict[str, Any]:
    """Direct query function"""
    async with EchoBrainClient() as client:
        return await client.query(query, **kwargs)

async def echo_generate_workflow(prompt: str, **kwargs) -> Dict[str, Any]:
    """Direct workflow generation function"""
    async with EchoBrainClient() as client:
        return await client.generate_workflow(prompt, **kwargs)

async def echo_classify_intent(user_input: str) -> Dict[str, Any]:
    """Direct intent classification function"""
    async with EchoBrainClient() as client:
        return await client.classify_intent(user_input)