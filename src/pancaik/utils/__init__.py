"""Utility modules for the Pancaik application."""

# Make the directory a proper package

# Export image generation function
from pancaik.utils.ai_images import generate_image

# Export key functions from ai_router
from pancaik.utils.ai_router import (
    AIRouter,
    MessageDict,
    Provider,
    compose_prompt,
    default_router,
    get_completion,
    openrouter,
)

__all__ = [
    "get_completion",
    "compose_prompt",
    "generate_image",
    "AIRouter",
    "MessageDict",
    "Provider",
    "default_router",
    "openrouter",
]
