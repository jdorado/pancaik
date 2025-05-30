"""
Image generation tool for Pancaik agents using AI.
"""

from typing import Any, Dict, Optional
import os
import io
from PIL import Image
from google import genai
from google.genai import types

from ..core.config import logger
from ..core.ai_logger import ai_logger
from ..utils.ai_router import get_completion
from ..utils.json_parser import extract_json_content
from ..utils.prompt_utils import get_prompt
from ..utils.context_utils import find_and_extract_context_key
from .base import tool


@tool()
async def image_generator(
    data_store: Dict[str, Any], 
    image_style: Optional[str] = None,
    image_context: Optional[str] = None,
    image_prompt_guidelines: Optional[str] = None,
    image_generation_type: str = "contextual"
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
        image_generation_type: Choose between 'contextual' (gemini-2.0-flash-preview-image-generation) or 'artistic' (imagen-3.0-generate-002)

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
        f"Starting image generation process. Type: {image_generation_type}",
        agent_id, account_id, agent_name
    )

    # --- Tool logic: Image generation using Google Gemini API ---
    
    # Get context and check for media_data with images and use the last one for image generation
    context = data_store.get("context", {})
    input_image = None
    if "media_data" in context and context["media_data"]:
        # Select the last image from media_data
        for media_item in reversed(context["media_data"]):
            if media_item.get("mediaType", "").startswith("image/"):
                # Convert byte array back to bytes for the API
                image_bytes = bytes(media_item["data"])
                # Create PIL Image object for Gemini API
                input_image = Image.open(io.BytesIO(image_bytes))
                ai_logger.action(f"Found image in context media_data, will use as input for image generation", agent_id, account_id, agent_name)
                break
        
        # Remove media_data from context after using it
        updated_context = {k: v for k, v in context.items() if k != "media_data"}
    else:
        updated_context = context

    context_image_style, updated_context = find_and_extract_context_key(updated_context, "image style")
    
    # Use context image style if found, otherwise use parameter
    final_image_style = context_image_style if context_image_style is not None else image_style
    
    # Force input_image to None for artistic model since it doesn't accept input images
    if image_generation_type == "artistic" and input_image is not None:
        ai_logger.action("Setting input image to None for artistic model (doesn't support input images)", agent_id, account_id, agent_name)
        input_image = None
    
    if context_image_style:
        ai_logger.action(f"Found image style in context", agent_id, account_id, agent_name)
    elif image_style:
        ai_logger.action(f"Using provided image style", agent_id, account_id, agent_name)
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
    
    # Generate prompt based on whether image is provided
    if input_image is not None:
        # If image is provided, combine available elements without AI generation
        prompt_data = {}
        
        if final_context:
            prompt_data["context"] = final_context
        
        if final_image_style:
            prompt_data["image_style"] = final_image_style
            
        if image_prompt_guidelines:
            prompt_data["image_prompt_guidelines"] = image_prompt_guidelines
        
        if prompt_data:
            generated_prompt = get_prompt(prompt_data)
        else:
            generated_prompt = "Generate an enhanced version of this image"
            
        ai_logger.action("Combined available elements for image-based generation (no AI prompt generation)", agent_id, account_id, agent_name)
    else:
        # No image provided, use AI to generate detailed prompt
        ai_logger.action("Generating detailed image prompt using AI", agent_id, account_id, agent_name)
        
        output_format = """\nOUTPUT IN JSON: Strict JSON format, no additional text.\n"image_prompt": "Your detailed image generation prompt here"\n"""
        prompt_data = {
            "task": "Generate a detailed image prompt for AI image generation based on the provided style and context.",
            "context": final_context,
        }
        
        # Add image_style if provided
        if final_image_style:
            prompt_data["image_style"] = final_image_style
        
        # Add image_prompt_guidelines if provided
        if image_prompt_guidelines:
            prompt_data["image_prompt_guidelines"] = image_prompt_guidelines
            ai_logger.thinking("Applying custom prompt guidelines", agent_id, account_id, agent_name)
        
        # Add output_format as the last key
        prompt_data["output_format"] = output_format
        
        prompt = get_prompt(prompt_data)
        model_id = config.get("ai_models", {}).get("default")
        response = await get_completion(prompt=prompt, model_id=model_id)

        # Parse the response as strict JSON
        parsed_response = extract_json_content(response) or {}
        generated_prompt = parsed_response.get("image_prompt", "Create a professional image")
        
        ai_logger.result(f"Generated image prompt using AI", agent_id, account_id, agent_name)
    
    # Initialize Gemini client
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        ai_logger.error("GEMINI_API_KEY environment variable is required for image generation", agent_id, account_id, agent_name)
        raise ValueError("GEMINI_API_KEY environment variable is required")
    
    client = genai.Client(api_key=api_key)

    # Determine the model and config based on image_generation_type
    if image_generation_type == "contextual":
        model_name = "gemini-2.0-flash-preview-image-generation"
        config = types.GenerateContentConfig(
            response_modalities=['TEXT', 'IMAGE']
        )
        ai_logger.action("Using contextual model for smart, context-aware generation", agent_id, account_id, agent_name)
    else:  # artistic
        model_name = "imagen-3.0-generate-002"
        config = types.GenerateImagesConfig(
            number_of_images=1,
            output_mime_type="image/jpeg",
            person_generation="ALLOW_ADULT",
            aspect_ratio="4:3",
        )
        ai_logger.action("Using artistic model for high-quality, photorealistic generation", agent_id, account_id, agent_name)

    # Generate images
    if image_generation_type == "contextual":
        # For contextual model, include image in contents if available
        if input_image:
            contents = [input_image, generated_prompt]
        else:
            contents = generated_prompt
            
        result = await client.aio.models.generate_content(
            model=model_name,
            contents=contents,
            config=config,
        )
    else:
        # For artistic model - imagen-3.0 may not support input images the same way
        # Fall back to text-only generation for artistic model
        result = await client.aio.models.generate_images(
            model=model_name,
            prompt=generated_prompt,
            config=config,
        )

    # Process results
    generated_images = []
    if image_generation_type == "contextual":
        # Process contextual model results
        if result.candidates and len(result.candidates) > 0:
            candidate = result.candidates[0]
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        image_byte_array = list(part.inline_data.data)
                        generated_images.append({
                            'data': image_byte_array,
                            'mediaType': part.inline_data.mime_type or 'image/jpeg'
                        })
    else:
        # Process artistic model results
        if result.generated_images:
            for generated_image in result.generated_images:
                image_byte_array = list(generated_image.image.image_bytes)
                generated_images.append({
                    'data': image_byte_array,
                    'mediaType': 'image/jpeg'
                })

    if generated_images:
        ai_logger.result(f"Successfully generated {len(generated_images)} image(s) in JPEG format", agent_id, account_id, agent_name)
    else:
        ai_logger.warning("No images were generated by the AI model", agent_id, account_id, agent_name)

    context = {'media_data': generated_images}
    
    # Return in the required format for Pancaik tools
    return {
        "values": {
            "context": context,
            "output": context,
        },
    } 