#!/usr/bin/env python3
"""
Echo Integration API - Command Interface for Intelligent Anime Production

This API provides the command interface layer that connects user interactions
(Telegram, Browser, API calls) to the Echo Orchestration Engine for intelligent
creative workflows with persistent learning.

Author: Claude Code + Patrick Vestal
Created: 2025-12-11
Branch: feature/echo-orchestration-engine
"""

import asyncio
import json
import logging
import os

# Import our Echo orchestration engine
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.echo_orchestration_engine import (
    EchoOrchestrationEngine,
    InteractionSource,
    UserIntent,
    WorkflowType,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================================
# PYDANTIC MODELS FOR API
# ================================


class EchoCommand(BaseModel):
    """Base command model for Echo interactions"""

    command: str = Field(..., description="The command to execute")
    source: str = Field(
        default="api",
        description="Source of the command (telegram, browser_studio, api)",
    )
    user_id: str = Field(..., description="User identifier")
    project_id: Optional[str] = Field(None, description="Project context")
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Command parameters"
    )
    context: Dict[str, Any] = Field(
        default_factory=dict, description="Additional context"
    )


class ProjectCreationRequest(BaseModel):
    """Request model for creating new projects"""

    project_name: str = Field(..., description="Name of the project")
    genre: str = Field(default="anime", description="Project genre")
    style_preferences: Dict[str, Any] = Field(
        default_factory=dict, description="Style preferences"
    )
    initial_characters: List[str] = Field(
        default_factory=list, description="Initial character list"
    )


class CharacterGenerationRequest(BaseModel):
    """Request model for character generation"""

    character_name: str = Field(..., description="Character name")
    project_id: str = Field(..., description="Project ID")
    style_override: Optional[Dict[str, Any]] = Field(
        None, description="Style overrides"
    )
    scene_context: str = Field(default="portrait", description="Scene context")
    consistency_mode: bool = Field(
        default=True, description="Enable consistency checking"
    )


class StyleLearningRequest(BaseModel):
    """Request model for style learning"""

    style_name: str = Field(..., description="Name of the style")
    example_images: List[str] = Field(..., description="Example image paths")
    style_description: str = Field(..., description="Description of the style")
    apply_to_project: Optional[str] = Field(
        None, description="Apply to specific project"
    )


class EchoResponse(BaseModel):
    """Standard response model for Echo interactions"""

    success: bool
    orchestration_id: str
    result: Dict[str, Any] = Field(default_factory=dict)
    learned_adaptations: Dict[str, Any] = Field(default_factory=dict)
    next_suggestions: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    processing_time_ms: Optional[int] = None


# ================================
# FASTAPI APPLICATION
# ================================

app = FastAPI(
    title="Echo Integration API",
    description="Intelligent Anime Production with Persistent Learning",
    version="2.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Echo engine instance
echo_engine: Optional[EchoOrchestrationEngine] = None

# ================================
# APPLICATION STARTUP
# ================================


@app.on_event("startup")
async def startup_event():
    """Initialize Echo Orchestration Engine on startup"""
    global echo_engine

    try:
        # Database configuration
        db_config = {
            "host": "localhost",
            "database": "anime_production",
            "user": "patrick",
            "password": "tower_echo_brain_secret_key_2025",
        }

        # Redis configuration
        redis_config = {"host": "localhost", "port": 6379, "db": 0}

        # Initialize Echo engine
        echo_engine = EchoOrchestrationEngine(db_config, redis_config)

        logger.info("🚀 Echo Integration API started - Intelligent workflows ready!")

    except Exception as e:
        logger.error(f"Failed to initialize Echo engine: {e}")
        echo_engine = None


# ================================
# COMMAND INTERFACE ENDPOINTS
# ================================


@app.post("/api/echo/command", response_model=EchoResponse)
async def execute_echo_command(command: EchoCommand, background_tasks: BackgroundTasks):
    """
    Main command interface for Echo - handles all intelligent workflow requests

    This is the primary endpoint that interprets commands and orchestrates
    intelligent workflows with learning and adaptation.
    """
    start_time = datetime.now()

    if not echo_engine:
        raise HTTPException(status_code=500, detail="Echo engine not initialized")

    try:
        # Parse command into UserIntent
        user_intent = parse_command_to_intent(command)

        # Orchestrate the workflow
        result = await echo_engine.orchestrate_user_request(user_intent)

        # Calculate processing time
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)

        return EchoResponse(
            success=result["success"],
            orchestration_id=result["orchestration_id"],
            result=result.get("result", {}),
            learned_adaptations=result.get("learned_adaptations", {}),
            next_suggestions=result.get("next_suggestions", []),
            error=result.get("error"),
            processing_time_ms=processing_time,
        )

    except Exception as e:
        logger.error(f"Command execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/echo/generate/character", response_model=EchoResponse)
async def generate_character_intelligent(
    request: CharacterGenerationRequest, user_id: str
):
    """
    Intelligent character generation with consistency learning

    This endpoint uses Echo's orchestration to generate characters that are
    consistent with previous generations and user preferences.
    """
    command = EchoCommand(
        command="generate_character",
        source="api",
        user_id=user_id,
        project_id=request.project_id,
        parameters={
            "character_name": request.character_name,
            "scene_context": request.scene_context,
            "consistency_mode": request.consistency_mode,
            "style_override": request.style_override,
        },
    )

    return await execute_echo_command(command, BackgroundTasks())


@app.post("/api/echo/project/create", response_model=EchoResponse)
async def create_intelligent_project(request: ProjectCreationRequest, user_id: str):
    """
    Create new project with intelligent setup and style learning

    Echo analyzes the request and sets up the project with appropriate
    style templates and character archetypes based on user preferences.
    """
    command = EchoCommand(
        command="create_project",
        source="api",
        user_id=user_id,
        parameters={
            "project_name": request.project_name,
            "genre": request.genre,
            "style_preferences": request.style_preferences,
            "initial_characters": request.initial_characters,
        },
    )

    return await execute_echo_command(command, BackgroundTasks())


@app.post("/api/echo/style/learn", response_model=EchoResponse)
async def learn_style_intelligent(request: StyleLearningRequest, user_id: str):
    """
    Learn new style from examples with Echo intelligence

    Echo analyzes the provided examples and creates a learnable style
    profile that can be applied to future generations.
    """
    command = EchoCommand(
        command="learn_style",
        source="api",
        user_id=user_id,
        project_id=request.apply_to_project,
        parameters={
            "style_name": request.style_name,
            "example_images": request.example_images,
            "style_description": request.style_description,
        },
    )

    return await execute_echo_command(command, BackgroundTasks())


# ================================
# TELEGRAM INTEGRATION ENDPOINTS
# ================================


@app.post("/api/echo/telegram/command")
async def handle_telegram_command(request: Dict[str, Any]):
    """
    Handle commands from Telegram bot with context awareness

    This endpoint provides the bridge between Telegram interactions
    and Echo's intelligent workflow orchestration.
    """
    try:
        # Extract Telegram command details
        telegram_user_id = request.get("user_id")
        message_text = request.get("message", "")
        chat_context = request.get("context", {})

        # Parse Telegram command
        command = parse_telegram_command(message_text, telegram_user_id, chat_context)

        if not command:
            return {"success": False, "error": "Could not parse command"}

        # Execute via main command interface
        return await execute_echo_command(command, BackgroundTasks())

    except Exception as e:
        logger.error(f"Telegram command handling failed: {e}")
        return {"success": False, "error": str(e)}


# ================================
# USER PREFERENCE ENDPOINTS
# ================================


@app.get("/api/echo/user/{user_id}/preferences")
async def get_user_preferences(user_id: str):
    """Get user's creative preferences and learned styles"""
    if not echo_engine:
        raise HTTPException(status_code=500, detail="Echo engine not initialized")

    try:
        user_context = await echo_engine.load_user_creative_context(user_id)
        return {
            "success": True,
            "user_profile": user_context["user_profile"],
            "active_styles": user_context["active_styles"],
            "adaptive_preferences": user_context["adaptive_preferences"],
        }

    except Exception as e:
        logger.error(f"Failed to get user preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/echo/user/{user_id}/preferences/update")
async def update_user_preferences(user_id: str, preferences: Dict[str, Any]):
    """Update user's creative preferences"""
    if not echo_engine:
        raise HTTPException(status_code=500, detail="Echo engine not initialized")

    try:
        await echo_engine.update_user_creative_dna(user_id, preferences)
        return {"success": True, "message": "Preferences updated successfully"}

    except Exception as e:
        logger.error(f"Failed to update user preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ================================
# PROJECT MANAGEMENT ENDPOINTS
# ================================


@app.get("/api/echo/projects/{user_id}")
async def get_user_projects(user_id: str):
    """Get all projects for a user with latest context"""
    if not echo_engine:
        raise HTTPException(status_code=500, detail="Echo engine not initialized")

    try:
        # This would query the project_memory table for user's projects
        # Implementation depends on database query method
        return {
            "success": True,
            "projects": [],
            "message": "Project listing not yet implemented",
        }

    except Exception as e:
        logger.error(f"Failed to get user projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/echo/project/{project_id}/context")
async def get_project_context(project_id: str):
    """Get complete project context for Echo workflows"""
    if not echo_engine:
        raise HTTPException(status_code=500, detail="Echo engine not initialized")

    try:
        project_context = await echo_engine.load_project_context(project_id)
        return {"success": True, "project_context": project_context}

    except Exception as e:
        logger.error(f"Failed to get project context: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ================================
# ANALYTICS AND LEARNING ENDPOINTS
# ================================


@app.get("/api/echo/analytics/{user_id}")
async def get_user_analytics(user_id: str):
    """Get user's creative analytics and learning insights"""
    if not echo_engine:
        raise HTTPException(status_code=500, detail="Echo engine not initialized")

    try:
        # Query echo_intelligence table for user analytics
        # This would show learning patterns, success rates, style evolution
        return {
            "success": True,
            "analytics": {},
            "message": "Analytics not yet implemented",
        }

    except Exception as e:
        logger.error(f"Failed to get user analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/echo/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy" if echo_engine else "degraded",
        "service": "echo-integration-api",
        "version": "2.0.0",
        "features": {
            "intelligent_workflows": echo_engine is not None,
            "persistent_learning": True,
            "style_adaptation": True,
            "character_consistency": True,
        },
        "timestamp": datetime.now().isoformat(),
    }


# ================================
# UTILITY FUNCTIONS
# ================================


def parse_command_to_intent(command: EchoCommand) -> UserIntent:
    """Parse API command into UserIntent for Echo orchestration"""

    # Map command strings to actions and targets
    command_mapping = {
        "generate_character": ("generate", "character"),
        "generate_scene": ("generate", "scene"),
        "create_project": ("create", "project"),
        "continue_project": ("continue", "project"),
        "learn_style": ("learn", "style"),
        "refine_style": ("refine", "style"),
        "batch_generate": ("generate", "batch"),
    }

    action, target = command_mapping.get(command.command, ("generate", "character"))

    # Map source string to enum
    source_mapping = {
        "telegram": InteractionSource.TELEGRAM,
        "browser_studio": InteractionSource.BROWSER_STUDIO,
        "api": InteractionSource.API,
        "scheduled": InteractionSource.SCHEDULED,
    }

    source = source_mapping.get(command.source, InteractionSource.API)

    # Build context from parameters and context
    context = {**command.parameters, **command.context}

    return UserIntent(
        action=action,
        target=target,
        context=context,
        source=source,
        user_id=command.user_id,
        project_id=command.project_id,
    )


def parse_telegram_command(
    message_text: str, user_id: str, chat_context: Dict
) -> Optional[EchoCommand]:
    """Parse Telegram message into Echo command"""

    # Basic Telegram command parsing
    if message_text.startswith("/generate"):
        # Example: "/generate character Yuki in cyberpunk style"
        parts = message_text.split()
        if len(parts) >= 3:
            target = parts[1]  # 'character'
            name = parts[2]  # 'Yuki'
            style_hint = " ".join(parts[3:]) if len(parts) > 3 else ""

            return EchoCommand(
                command=f"generate_{target}",
                source="telegram",
                user_id=user_id,
                parameters={"character_name": name, "style_hint": style_hint},
                context=chat_context,
            )

    elif message_text.startswith("/project"):
        # Example: "/project create Cyberpunk Academy"
        parts = message_text.split()
        if len(parts) >= 3:
            action = parts[1]  # 'create'
            project_name = " ".join(parts[2:])  # 'Cyberpunk Academy'

            return EchoCommand(
                command=f"{action}_project",
                source="telegram",
                user_id=user_id,
                parameters={"project_name": project_name},
                context=chat_context,
            )

    elif message_text.startswith("/style"):
        # Example: "/style learn dramatic_lighting from scene_12.jpg"
        parts = message_text.split()
        if len(parts) >= 4:
            action = parts[1]  # 'learn'
            style_name = parts[2]  # 'dramatic_lighting'
            # Parse rest as examples or description

            return EchoCommand(
                command=f"{action}_style",
                source="telegram",
                user_id=user_id,
                parameters={
                    "style_name": style_name,
                    "style_description": " ".join(parts[3:]),
                },
                context=chat_context,
            )

    return None


# ================================
# MAIN APPLICATION
# ================================

if __name__ == "__main__":
    uvicorn.run(
        "echo_integration_api:app",
        host="0.0.0.0",
        port=8332,  # New port for Echo Integration API
        reload=True,
        log_level="info",
    )
