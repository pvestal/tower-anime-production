"""Prompt testing package — A/B test prompts, engines, and LoRA stacks."""
from .router import router as testing_router
from .pipeline_router import router as pipeline_router

# Include pipeline test routes under the same /api/testing prefix
testing_router.include_router(pipeline_router)

__all__ = ["testing_router"]
