"""
API routers for Tower Anime Production
"""

from .generation import router as generation_router
from .projects import router as projects_router

__all__ = [
    "generation_router",
    "projects_router",
]