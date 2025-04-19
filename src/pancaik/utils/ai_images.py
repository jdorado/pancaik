"""AI image generation utilities.

This module provides image generation capabilities using OpenAI.
"""

import asyncio

from pancaik.core.config import logger
from pancaik.utils.ai_router import Provider, default_router


async def generate_image(
    prompt: str,
    model_id: str = "dall-e-3",
    size: str = "1024x1024",
    quality: str = "standard",
    style: str = "vivid",
    retry_on_error: bool = True,
    retry_delay: int = 10,
    attempts: int = 0,
    max_attempts: int = 3,
) -> str:
    """Generate an image using OpenAI.

    Args:
        prompt: The text prompt for image generation
        model_id: The model ID to use (e.g., "dall-e-3")
        size: Image size (e.g., "1024x1024")
        quality: Image quality ("standard" or "hd")
        style: Image style ("vivid" or "natural")
        retry_on_error: Whether to retry on rate limit errors
        retry_delay: Seconds to wait before retrying
        attempts: Current attempt count (internal use)
        max_attempts: Maximum retry attempts

    Returns:
        URL of the generated image
    """
    assert prompt, "Prompt cannot be empty"
    assert model_id.startswith("dall-e-"), f"Invalid model ID: {model_id}. Must be a DALL-E model."

    try:
        async with default_router.get_client(Provider.OPENAI) as client:
            response = await client.images.generate(
                model=model_id,
                prompt=prompt,
                size=size,
                quality=quality,
                style=style,
                n=1,
            )
            return response.data[0].url

    except Exception as e:
        if getattr(e, "status_code", None) == 429 and retry_on_error and attempts < max_attempts:
            # Rate limit error, retry after delay
            logger.warning(f"Rate limit exceeded for image generation. Retrying in {retry_delay}s ({attempts+1}/{max_attempts})")
            await asyncio.sleep(retry_delay)
            return await generate_image(
                prompt=prompt,
                model_id=model_id,
                size=size,
                quality=quality,
                style=style,
                retry_on_error=retry_on_error,
                retry_delay=retry_delay,
                attempts=attempts + 1,
                max_attempts=max_attempts,
            )
        elif getattr(e, "status_code", None) == 400 and "content" in str(e).lower() and attempts == 0:
            # Content policy violation, try with safer prompt
            logger.warning("Content policy violation in image generation. Trying with safer prompt.")
            return await generate_image(
                prompt=f"Safe image, {prompt}",
                model_id=model_id,
                size=size,
                quality=quality,
                style=style,
                retry_on_error=retry_on_error,
                retry_delay=retry_delay,
                attempts=attempts + 1,
                max_attempts=max_attempts,
            )
        else:
            # Other error
            logger.error(f"Error in image generation: {str(e)}")
            raise
