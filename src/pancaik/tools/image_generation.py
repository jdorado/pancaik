"""
Image generation tool for Pancaik agents using AI.
"""

from typing import Any, Dict, Optional, Union
import os
import io
from PIL import Image
from google import genai
from google.genai import types
from openai import AsyncOpenAI
import base64

from ..core.config import logger
from ..core.ai_logger import ai_logger
from ..utils.ai_router import get_completion, compose_multimodal_prompt
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
        image_generation_type: Choose between 'contextual' (gemini-2.0-flash-preview-image-generation), 'artistic' (imagen-3.0-generate-002), or 'grok_image_generation' (grok-2-image-1212).

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

    # --- Tool logic: Image generation ---
    
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
    
    # --- Generate content/prompts based on model type ---
    
    generated_images = []

    if image_generation_type == "contextual" or image_generation_type == "artistic":
        gemini_api_key = os.environ.get("GEMINI_API_KEY")
        if not gemini_api_key:
            ai_logger.error("GEMINI_API_KEY environment variable is required for Gemini image generation", agent_id, account_id, agent_name)
            raise ValueError("GEMINI_API_KEY environment variable is required for Gemini image generation")
        gemini_client = genai.Client(api_key=gemini_api_key)

    if image_generation_type == "contextual":
        model_name = "gemini-2.0-flash-preview-image-generation"
        generation_config = types.GenerateContentConfig(
            response_modalities=['TEXT', 'IMAGE']
        )
        ai_logger.action("Using contextual model for smart, context-aware generation", agent_id, account_id, agent_name)
        
        contents = await _generate_contextual_content(
            final_context, final_image_style, image_prompt_guidelines, 
            input_image, agent_id, account_id, agent_name, config
        )
        
        gemini_result = await gemini_client.aio.models.generate_content(
            model=model_name,
            contents=contents,
            config=generation_config,
        )
        
        if gemini_result.candidates and len(gemini_result.candidates) > 0:
            candidate = gemini_result.candidates[0]
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        image_byte_array = list(part.inline_data.data)
                        generated_images.append({
                            'data': image_byte_array,
                            'mediaType': part.inline_data.mime_type or 'image/jpeg'
                        })
        
    elif image_generation_type == "artistic":
        model_name = "imagen-3.0-generate-002"
        generation_config = types.GenerateImagesConfig(
            number_of_images=1,
            output_mime_type="image/jpeg",
            person_generation="ALLOW_ADULT",
            aspect_ratio="4:3",
        )
        ai_logger.action("Using artistic model for high-quality, photorealistic generation", agent_id, account_id, agent_name)
        
        generated_prompt = await _generate_prompt_for_artistic(
            final_context, final_image_style, image_prompt_guidelines,
            input_image, agent_id, account_id, agent_name, config
        )
        
        gemini_result = await gemini_client.aio.models.generate_images(
            model=model_name,
            prompt=generated_prompt,
            config=generation_config,
        )

        if gemini_result.generated_images:
            for generated_image_obj in gemini_result.generated_images:
                image_byte_array = list(generated_image_obj.image.image_bytes)
                generated_images.append({
                    'data': image_byte_array,
                    'mediaType': 'image/jpeg'
                })
    
    elif image_generation_type == "grok_image_generation":
        ai_logger.action("Using Grok model for image generation", agent_id, account_id, agent_name)
        
        XAI_API_KEY = os.environ.get("GROK_API_KEY")
        if not XAI_API_KEY:
            ai_logger.error("GROK_API_KEY environment variable is required for Grok image generation", agent_id, account_id, agent_name)
            raise ValueError("GROK_API_KEY environment variable is required for Grok image generation")

        grok_client = AsyncOpenAI(base_url="https://api.x.ai/v1", api_key=XAI_API_KEY)
        grok_model_name = "grok-2-image-1212"

        generated_grok_prompt = await _generate_prompt_for_artistic(
            final_context, final_image_style, image_prompt_guidelines,
            input_image, agent_id, account_id, agent_name, config
        )
        ai_logger.action(f"Generated prompt for Grok (original length: {len(generated_grok_prompt)})", agent_id, account_id, agent_name)

        # Truncate prompt if it exceeds the maximum allowed length
        MAX_GROK_PROMPT_LENGTH = 1024
        if len(generated_grok_prompt) > MAX_GROK_PROMPT_LENGTH:
            original_length = len(generated_grok_prompt)
            generated_grok_prompt = generated_grok_prompt[:MAX_GROK_PROMPT_LENGTH]
            ai_logger.warning(
                f"Grok prompt was truncated from {original_length} to {MAX_GROK_PROMPT_LENGTH} characters to meet model limits.",
                agent_id, account_id, agent_name
            )
            ai_logger.action(f"Truncated prompt for Grok: '{generated_grok_prompt}'", agent_id, account_id, agent_name)


        try:
            grok_response = await grok_client.images.generate(
                model=grok_model_name,
                prompt=generated_grok_prompt,
                n=1,
                response_format="b64_json"
            )

            if grok_response.data:
                for img_data in grok_response.data:
                    if img_data.b64_json:
                        img_bytes = base64.b64decode(img_data.b64_json)
                        image_byte_array = list(img_bytes)
                        generated_images.append({
                            'data': image_byte_array,
                            'mediaType': 'image/png' 
                        })
            if not generated_images: # Check if any images were actually added after the loop
                 ai_logger.warning("Grok model call succeeded but returned no image data.", agent_id, account_id, agent_name)

        except Exception as e:
            ai_logger.error(f"Error during Grok image generation with X.AI API: {e}", agent_id, account_id, agent_name)
            # This will lead to "No images were generated" log message later if generated_images remains empty.
            
    else:
        ai_logger.error(f"Unknown image_generation_type: {image_generation_type}", agent_id, account_id, agent_name)
        raise ValueError(f"Unknown image_generation_type: {image_generation_type}. Supported types: contextual, artistic, grok_image_generation.")


    if generated_images:
        ai_logger.result(f"Successfully generated {len(generated_images)} image(s) using {image_generation_type} model.", agent_id, account_id, agent_name)
    else:
        ai_logger.warning(f"No images were generated by the {image_generation_type} AI model.", agent_id, account_id, agent_name)

    context_for_return = {'media_data': generated_images}
    
    return {
        "values": {
            "context": context_for_return,
            "output": context_for_return,
        },
    } 


async def _describe_image_for_prompt(input_image: Image.Image, agent_id: str, account_id: str, agent_name: str, config: Dict[str, Any]) -> str:
    """Generate a description of the input image to include in the artistic model prompt."""
    import base64
    import io
    
    # Convert PIL image to base64 for vision model
    buffer = io.BytesIO()
    input_image.save(buffer, format='JPEG')
    image_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    # Use vision model to describe the image
    describe_prompt = compose_multimodal_prompt(
        text="Describe this image in detail for use in an image generation prompt. Focus on visual elements, style, composition, colors, and mood.",
        images=[image_base64],
        image_format="jpeg"
    )
    
    model_id = config.get("ai_models", {}).get("default")
    description = await get_completion(prompt=describe_prompt, model_id=model_id)
    
    ai_logger.action("Generated image description for artistic model prompt", agent_id, account_id, agent_name)
    return description


async def _generate_prompt_for_artistic(
    final_context: Dict[str, Any], 
    final_image_style: Optional[str], 
    image_prompt_guidelines: Optional[str],
    input_image: Optional[Image.Image],
    agent_id: str, 
    account_id: str, 
    agent_name: str, 
    config: Dict[str, Any]
) -> str:
    """Generate a comprehensive prompt for the artistic model, including image description if available."""
    
    prompt_data = {
        "task": "Generate a detailed image prompt for AI image generation based on the provided style and context.",
        "context": final_context,
    }
    
    # Add image description if input image exists
    if input_image:
        image_description = await _describe_image_for_prompt(input_image, agent_id, account_id, agent_name, config)
        prompt_data["input_image_description"] = image_description
        ai_logger.action("Added image description to prompt generation", agent_id, account_id, agent_name)
    
    # Add style and guidelines
    if final_image_style:
        prompt_data["image_style"] = final_image_style
    
    if image_prompt_guidelines:
        prompt_data["image_prompt_guidelines"] = image_prompt_guidelines
    
    # Add output format
    prompt_data["output_format"] = """\nOUTPUT IN JSON: Strict JSON format, no additional text.\n"image_prompt": "Your detailed image generation prompt here"\n"""
    
    # Generate the prompt using AI
    prompt = get_prompt(prompt_data)
    model_id = config.get("ai_models", {}).get("default")
    response = await get_completion(prompt=prompt, model_id=model_id)
    
    # Parse the response
    parsed_response = extract_json_content(response) or {}
    generated_prompt = parsed_response.get("image_prompt", "Create a professional image")
    
    ai_logger.result("Generated comprehensive prompt for artistic model", agent_id, account_id, agent_name)
    return generated_prompt


async def _generate_contextual_content(
    final_context: Dict[str, Any],
    final_image_style: Optional[str], 
    image_prompt_guidelines: Optional[str],
    input_image: Optional[Image.Image],
    agent_id: str, 
    account_id: str, 
    agent_name: str,
    config: Dict[str, Any]
) -> Union[str, list]:
    """Generate content for contextual model (image + comprehensive prompt or just prompt)."""
    
    if input_image:
        # For contextual model with image: generate comprehensive prompt (like artistic) + pass image
        generated_prompt = await _generate_prompt_for_artistic(
            final_context, final_image_style, image_prompt_guidelines,
            input_image, agent_id, account_id, agent_name, config
        )
        
        ai_logger.action("Using image + comprehensive AI-generated prompt for contextual model", agent_id, account_id, agent_name)
        return [input_image, generated_prompt]
    else:
        # For contextual model without image: generate AI prompt based on context, style, guidelines
        output_format = """\nOUTPUT IN JSON: Strict JSON format, no additional text.\n"image_prompt": "Your detailed image generation prompt here"\n"""
        prompt_data = {
            "task": "Generate a detailed image prompt for AI image generation based on the provided style and context.",
            "context": final_context,
        }
        
        if final_image_style:
            prompt_data["image_style"] = final_image_style
        if image_prompt_guidelines:
            prompt_data["image_prompt_guidelines"] = image_prompt_guidelines
        
        prompt_data["output_format"] = output_format
        
        prompt = get_prompt(prompt_data)
        model_id = config.get("ai_models", {}).get("default")
        response = await get_completion(prompt=prompt, model_id=model_id)
        
        parsed_response = extract_json_content(response) or {}
        generated_prompt = parsed_response.get("image_prompt", "Create a professional image")
        
        ai_logger.result("Generated AI prompt for contextual model", agent_id, account_id, agent_name)
        return generated_prompt 