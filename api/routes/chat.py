"""Chat and conversation routes"""
from fastapi import APIRouter, HTTPException
from datetime import datetime
import uuid
import logging
import sys
import os
import asyncio

sys.path.insert(0, "/opt/tower-anime-production")

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/anime", tags=["chat"])

# Import services
conversation_memory = None
echo_client = None
workflow_generator = None

try:
    from services.conversation_memory import ConversationMemory
    conversation_memory = ConversationMemory()
    logger.info("Conversation memory initialized")
except Exception as e:
    logger.error(f"Failed to initialize conversation memory: {e}")

try:
    from services.echo_client import echo_query
except Exception as e:
    logger.error(f"Failed to import echo_query: {e}")

try:
    from services.workflow_generator import WorkflowGenerator
    workflow_generator = WorkflowGenerator()
except Exception as e:
    logger.error(f"Failed to initialize workflow generator: {e}")


@router.post("/chat")
async def chat_endpoint(message: dict):
    """Main chat endpoint with AI assistance"""
    
    msg_text = message.get("message", "")
    conversation_id = message.get("conversation_id") or f"chat_{uuid.uuid4().hex[:8]}"
    
    try:
        # Store user message
        if conversation_memory:
            conversation_memory.add_message(
                conversation_id=conversation_id,
                role="user",
                content=msg_text,
                metadata={"timestamp": datetime.now().isoformat()}
            )
        
        # Check if workflow is needed
        workflow_keywords = ["workflow", "parameters", "settings", "config", "generate", "animation", "video"]
        needs_workflow = any(keyword in msg_text.lower() for keyword in workflow_keywords)
        
        if needs_workflow and workflow_generator:
            # Generate workflow parameters
            workflow_type = workflow_generator.extract_workflow_type(msg_text)
            workflow_params = workflow_generator.generate_workflow(msg_text, workflow_type)
            
            response_text = f"""I'll help you with the workflow parameters.

**Type**: {workflow_type}
**Model**: {workflow_params['parameters']['model']}
**Seed**: {workflow_params['parameters']['seed']}
**Steps**: {workflow_params['parameters']['steps']}
**CFG Scale**: {workflow_params['parameters']['cfg_scale']}
**Sampler**: {workflow_params['parameters']['sampler']}"""
            
            if workflow_type == "video":
                video_settings = workflow_params['parameters'].get('video_settings', {})
                response_text += f"""
**Frames**: {video_settings.get('frames', 48)}
**FPS**: {video_settings.get('fps', 24)}
**Motion Scale**: {video_settings.get('motion_scale', 1.0)}"""
            
            response_text += "\n\nThese parameters are optimized for your request!"
        else:
            # Regular chat response with timeout
            try:
                response = await asyncio.wait_for(
                    echo_query(
                        query=msg_text,
                        model="tinyllama:latest",
                        conversation_id=conversation_id
                    ),
                    timeout=4.0
                )
                response_text = response.get("response", "How can I help with your anime production?")
            except asyncio.TimeoutError:
                response_text = "Processing your request..."
        
        # Store assistant response
        if conversation_memory:
            conversation_memory.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=response_text,
                metadata={"timestamp": datetime.now().isoformat()}
            )
        
        return {
            "response": response_text,
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/history/{conversation_id}")
async def get_conversation_history(conversation_id: str):
    """Get conversation history"""
    
    if not conversation_memory:
        raise HTTPException(status_code=503, detail="Conversation memory service not available")
    
    try:
        history = conversation_memory.get_conversation(conversation_id)
        return {"conversation_id": conversation_id, "messages": history}
    except Exception as e:
        logger.error(f"Failed to get history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
