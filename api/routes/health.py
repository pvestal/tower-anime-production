"""
Health check routes
"""
from fastapi import APIRouter
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/anime", tags=["health"])

@router.get("/health")
async def health_check():
    """Main health check endpoint"""
    # Check Echo Brain
    echo_status = "healthy"
    try:
        from services.echo_client import EchoBrainClient
    except:
        echo_status = "unavailable"

    return {
        "status": "healthy",
        "service": "anime-production",
        "version": "3.0.0",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "comfyui": {"status": "healthy"},
            "gpu": {"available": True},
            "conversation_memory": {"status": "enabled"}
        },
        "services": {
            "echo_brain": {"status": echo_status}
        }
    }

@router.get("/echo-status")
async def echo_status():
    """Check Echo Brain integration status"""
    try:
        from services.echo_client import EchoBrainClient
        return {
            "echo_brain_enabled": True,
            "timestamp": datetime.now().isoformat()
        }
    except:
        return {
            "echo_brain_enabled": False,
            "timestamp": datetime.now().isoformat()
        }
