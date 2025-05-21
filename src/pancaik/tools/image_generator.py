"""Image generation tool using AI providers.

This module provides a tool that leverages the generic image generation
utility to produce images from text prompts.
"""

from typing import Any, Dict

from ..core.ai_logger import ai_logger
from ..core.config import logger
from ..utils import generate_image
from .base import tool


@tool
async def image_generator(
    data_store: Dict[str, Any],
    prompt: str,
    model_id: str = "dall-e-3",
    size: str = "1024x1024",
    quality: str = "standard",
    style: str = "vivid",
) -> Dict[str, Any]:
    """Generate an image and store the resulting URL in context.

    Args:
        data_store: Agent's data store containing configuration and state
        prompt: Description of the desired image
        model_id: Model identifier for image generation (default: "dall-e-3")
        size: Image size (e.g., "1024x1024")
        quality: Image quality ("standard" or "hd")
        style: Image style ("vivid" or "natural")

    Returns:
        Dictionary with operation status and values for context and output
    """
    # Preconditions
    assert data_store is not None, "data_store must be provided"
    assert isinstance(prompt, str) and prompt, "prompt must be a non-empty string"

    agent_id = data_store.get("agent_id")
    config = data_store.get("config", {})
    account_id = config.get("account_id")
    agent_name = config.get("name")

    logger.info(f"Generating image for agent {agent_id} ({agent_name}) using {model_id}")
    ai_logger.action(f"Generating image with {model_id}", agent_id=agent_id, account_id=account_id, agent_name=agent_name)

    image_url = await generate_image(prompt=prompt, model_id=model_id, size=size, quality=quality, style=style)

    context = {"generated_image_url": image_url}

    ai_logger.result("Image generated successfully", agent_id=agent_id, account_id=account_id, agent_name=agent_name)

    return {
        "status": "success",
        "values": {"context": context, "output": context},
    }
