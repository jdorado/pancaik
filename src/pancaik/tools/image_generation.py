"""
Image generation tool for Pancaik agents using AI.
"""

from typing import Any, Dict, Optional, Tuple
import os
from google import genai
from google.genai import types

from ..core.config import logger
from ..core.ai_logger import ai_logger
from ..utils.ai_router import get_completion
from ..utils.json_parser import extract_json_content
from ..utils.prompt_utils import get_prompt
from .base import tool


def find_and_extract_context_key(context: Dict[str, Any], target_key: str) -> Tuple[Optional[Any], Dict[str, Any]]:
    """
    Find a key in context that contains the target key (case-insensitive, space-insensitive) and extract its value.
    
    Args:
        context: The context dictionary to search in
        target_key: The key to search for (e.g., "image style")
        
    Returns:
        Tuple of (found_value, updated_context) where updated_context has the key removed
    """
    if not context or not isinstance(context, dict):
        return None, context.copy() if context else {}
    
    # Normalize target key: lowercase and remove spaces
    normalized_target = target_key.lower().replace(" ", "")
    
    # Search for key containing the target
    found_key = None
    found_value = None
    
    for key in context.keys():
        if isinstance(key, str):
            normalized_key = key.lower().replace(" ", "")
            if normalized_target in normalized_key:
                found_key = key
                found_value = context[key]
                break
    
    # Create updated context without the found key
    updated_context = context.copy()
    if found_key:
        del updated_context[found_key]
    
    return found_value, updated_context


@tool()
async def image_generator(
    data_store: Dict[str, Any], 
    image_style: Optional[str] = None,
    image_context: Optional[str] = None,
    image_prompt_guidelines: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate images using AI based on context and custom prompts.
    
    Automatically creates visual content that complements your text content, 
    research findings, or social media posts.

    Args:
        data_store: Agent's data store containing configuration and state
        image_style: Define the visual style for the generated image (optional)
        image_context: Specify which part of the available context should be considered (optional)
        image_prompt_guidelines: Specify how the image prompt should be constructed (optional)

    Returns:
        Dictionary with operation status and values for context and output
    """
    # Preconditions (Design by Contract)
    assert data_store is not None, "data_store must be provided"

    agent_id = data_store.get("agent_id")
    config = data_store.get("config", {})
    account_id = config.get("account_id")
    agent_name = config.get("name")
    logger.info(f"Running image_generator for agent {agent_id} ({agent_name})")

    ai_logger.thinking(
        f"Starting image generation process. Style: {image_style or 'auto-detected'}, "
        f"Context filtering: {bool(image_context)}, Guidelines: {bool(image_prompt_guidelines)}",
        agent_id, account_id, agent_name
    )

    # --- Tool logic: Image generation using Google Gemini API ---
    
    # Get context and check for image style in context
    context = data_store.get("context", {})
    context_image_style, updated_context = find_and_extract_context_key(context, "image style")
    
    # Use context image style if found, otherwise use parameter
    final_image_style = context_image_style if context_image_style is not None else image_style
    
    if context_image_style:
        ai_logger.action(f"Found image style in context: '{context_image_style}'", agent_id, account_id, agent_name)
    elif image_style:
        ai_logger.action(f"Using provided image style: '{image_style}'", agent_id, account_id, agent_name)
    else:
        ai_logger.thinking("No specific image style provided, will generate based on context", agent_id, account_id, agent_name)
    
    # Extract relevant context if image_context instructions are provided
    final_context = updated_context
    if image_context is not None:
        ai_logger.action(f"Extracting relevant context using instructions: '{image_context}'", agent_id, account_id, agent_name)
        
        context_extraction_prompt_data = {
            "task": "Extract relevant context for image generation based on the provided instructions.",
            "full_context": updated_context,
            "extraction_instructions": image_context,
            "output_format": """\nOUTPUT IN JSON: Strict JSON format, no additional text.\n"extracted_context": {"key": "value", ...}\n"""
        }
        context_extraction_prompt = get_prompt(context_extraction_prompt_data)
        model_id = config.get("ai_models", {}).get("default")
        context_response = await get_completion(prompt=context_extraction_prompt, model_id=model_id)
        
        # Parse the context extraction response
        parsed_context_response = extract_json_content(context_response) or {}
        extracted_context = parsed_context_response.get("extracted_context", updated_context)
        final_context = extracted_context
        
        ai_logger.result(f"Context extraction completed. Extracted {len(final_context)} relevant elements", agent_id, account_id, agent_name)
    
    # Generate prompt based on image_style and context
    ai_logger.action("Generating detailed image prompt using AI", agent_id, account_id, agent_name)
    
    output_format = """\nOUTPUT IN JSON: Strict JSON format, no additional text.\n"image_prompt": "Your detailed image generation prompt here"\n"""
    prompt_data = {
        "task": "Generate a detailed image prompt for AI image generation based on the provided style and context.",
        "context": final_context,
    }
    
    # Add image_style as second key if provided
    if final_image_style:
        prompt_data["image_style"] = final_image_style
    
    # Add image_prompt_guidelines if provided
    if image_prompt_guidelines:
        prompt_data["image_prompt_guidelines"] = image_prompt_guidelines
        ai_logger.thinking(f"Applying custom prompt guidelines: '{image_prompt_guidelines}'", agent_id, account_id, agent_name)
    
    # Add output_format as the last key
    prompt_data["output_format"] = output_format
    
    prompt = get_prompt(prompt_data)
    model_id = config.get("ai_models", {}).get("default")
    response = await get_completion(prompt=prompt, model_id=model_id)

    # Parse the response as strict JSON
    parsed_response = extract_json_content(response) or {}
    generated_prompt = parsed_response.get("image_prompt", "Create a professional image")
    
    ai_logger.result(f"Generated image prompt: '{generated_prompt[:100]}{'...' if len(generated_prompt) > 100 else ''}'", agent_id, account_id, agent_name)
    
    # Initialize Gemini client
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        ai_logger.error("GEMINI_API_KEY environment variable is required for image generation", agent_id, account_id, agent_name)
        raise ValueError("GEMINI_API_KEY environment variable is required")
    
    ai_logger.action("Generating image using Google Gemini Imagen model", agent_id, account_id, agent_name)
    
    client = genai.Client(api_key=api_key)

    # Generate images
    result = await client.aio.models.generate_images(
        model="imagen-3.0-generate-002",
        prompt=generated_prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            output_mime_type="image/jpeg",
            person_generation="ALLOW_ADULT",
            aspect_ratio="4:3",
        ),
    )

    # Process results
    generated_images = []
    if result.generated_images:
        for generated_image in result.generated_images:
            # Convert image bytes to array of byte values
            image_byte_array = list(generated_image.image.image_bytes)
            generated_images.append({
                'data': image_byte_array,
                'mediaType': 'image/jpeg'
            })
        
        ai_logger.result(f"Successfully generated {len(generated_images)} image(s) in JPEG format", agent_id, account_id, agent_name)
    else:
        ai_logger.warning("No images were generated by the AI model", agent_id, account_id, agent_name)
    
    # Return in the required format for Pancaik tools
    return {
        "values": {
            "output": {
                'media_data': generated_images
            },
        },
    } 