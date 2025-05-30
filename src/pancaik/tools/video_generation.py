"""
Video generation tool for Pancaik agents using AI.
"""

from typing import Any, Dict, Optional
import os
import time
from google import genai
from google.genai import types
import asyncio
import uuid

from ..core.config import logger
from ..core.ai_logger import ai_logger
from ..utils.ai_router import get_completion
from ..utils.json_parser import extract_json_content
from ..utils.prompt_utils import get_prompt
from ..utils.context_utils import find_and_extract_context_key
from .base import tool


@tool()
async def video_generator(
    data_store: Dict[str, Any], 
    video_style: Optional[str] = None,
    video_context: Optional[str] = None,
    video_prompt_guidelines: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate videos using AI based on context and custom prompts.
    
    Creates dynamic visual content with camera movements, actions, and cinematic effects 
    that complement your content strategy.

    Args:
        data_store: Agent's data store containing configuration and state
        video_style: Define the visual and cinematic style for the generated video (optional)
        video_context: Specify which part of the available context should be considered (optional)
        video_prompt_guidelines: Specify how the video prompt should be constructed (optional)

    Returns:
        Dictionary with operation status and values for context and output
    """
    # Preconditions (Design by Contract)
    assert data_store is not None, "data_store must be provided"

    agent_id = data_store.get("agent_id")
    config = data_store.get("config", {})
    account_id = config.get("account_id")
    agent_name = config.get("name")
    logger.info(f"Running video_generator for agent {agent_id} ({agent_name})")

    ai_logger.thinking(
        f"Starting video generation process using AI video model",
        agent_id, account_id, agent_name
    )

    # --- Tool logic: Video generation using Google Gemini Veo API ---
    
    # Get context and check for video style in context
    context = data_store.get("context", {})
    context_video_style, updated_context = find_and_extract_context_key(context, "video style")
    
    # Use context video style if found, otherwise use parameter
    final_video_style = context_video_style if context_video_style is not None else video_style
    
    if context_video_style:
        ai_logger.action(f"Found video style in context", agent_id, account_id, agent_name)
    elif video_style:
        ai_logger.action(f"Using provided video style", agent_id, account_id, agent_name)
    else:
        ai_logger.thinking("No specific video style provided, will generate based on context", agent_id, account_id, agent_name)
    
    # Extract relevant context if video_context instructions are provided
    final_context = updated_context
    if video_context is not None:
        ai_logger.action(f"Extracting relevant context using instructions: '{video_context}'", agent_id, account_id, agent_name)
        
        context_extraction_prompt_data = {
            "task": "Extract relevant context for video generation based on the provided instructions.",
            "full_context": updated_context,
            "extraction_instructions": video_context,
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
    
    # Generate prompt based on video_style and context
    ai_logger.action("Generating detailed video prompt using AI", agent_id, account_id, agent_name)
    
    output_format = """\nOUTPUT IN JSON: Strict JSON format, no additional text.\n"video_prompt": "Your detailed video generation prompt here"\n"""
    prompt_data = {
        "task": "Generate a detailed video prompt for AI video generation based on the provided style and context.",
        "context": final_context,
    }
    
    # Add video_style as second key if provided
    if final_video_style:
        prompt_data["video_style"] = final_video_style
    
    # Add video_prompt_guidelines if provided
    if video_prompt_guidelines:
        prompt_data["video_prompt_guidelines"] = video_prompt_guidelines
        ai_logger.thinking("Applying custom prompt guidelines", agent_id, account_id, agent_name)
    
    # Add output_format as the last key
    prompt_data["output_format"] = output_format
    
    prompt = get_prompt(prompt_data)
    model_id = config.get("ai_models", {}).get("default")
    response = await get_completion(prompt=prompt, model_id=model_id)

    # Parse the response as strict JSON
    parsed_response = extract_json_content(response) or {}
    generated_prompt = parsed_response.get("video_prompt", "Create a professional video")
    
    ai_logger.result(f"Generated video prompt", agent_id, account_id, agent_name)
    
    # Initialize Gemini client
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        ai_logger.error("GEMINI_API_KEY environment variable is required for video generation", agent_id, account_id, agent_name)
        raise ValueError("GEMINI_API_KEY environment variable is required")
    
    client = genai.Client(
        http_options={"api_version": "v1beta"},
        api_key=api_key,
    )

    # Configure video generation settings
    video_config = types.GenerateVideosConfig(
        person_generation="allow_all",  # supported values: "dont_allow" or "allow_adult" or "allow_all"
        aspect_ratio="16:9",  # supported values: "16:9" or "16:10"
        number_of_videos=1,  # supported values: 1 - 4
        duration_seconds=5,  # supported values: 5 - 8
    )
    
    ai_logger.action("Starting video generation with AI model", agent_id, account_id, agent_name)

    # Generate video
    operation = await client.aio.models.generate_videos(
        model="veo-2.0-generate-001",
        prompt=generated_prompt,
        config=video_config,
    )

    # Wait for the video to be generated
    ai_logger.thinking("Waiting for video generation to complete...", agent_id, account_id, agent_name)
    while not operation.done:
        ai_logger.thinking("Video generation in progress, checking again in 10 seconds...", agent_id, account_id, agent_name)
        await asyncio.sleep(10)
        operation = await client.aio.operations.get(operation)

    result = operation.result
    if not result:
        ai_logger.error("Error occurred while generating video", agent_id, account_id, agent_name)
        return {
            "values": {
                "output": {
                    'media_data': []
                },
            },
        }

    generated_videos = result.generated_videos
    if not generated_videos:
        ai_logger.warning("No videos were generated by the AI model", agent_id, account_id, agent_name)
        return {
            "values": {
                "output": {
                    'media_data': []
                },
            },
        }

    # Process results
    video_data = []
    ai_logger.result(f"Generated {len(generated_videos)} video(s)", agent_id, account_id, agent_name)
    
    for n, generated_video in enumerate(generated_videos):
        ai_logger.action(f"Processing video {n+1}: {generated_video.video.uri}", agent_id, account_id, agent_name)
        
        # Get the event loop for running blocking operations in thread pool
        loop = asyncio.get_event_loop()
        
        # Download the video file first (run in thread pool)
        await loop.run_in_executor(None, lambda: client.files.download(file=generated_video.video))
        
        # Create unique filename to avoid conflicts
        unique_id = str(uuid.uuid4())[:8]
        video_filename = f"video_{agent_id}_{unique_id}_{n}.mp4"
        
        # Save the downloaded video (run in thread pool)
        await loop.run_in_executor(None, generated_video.video.save, video_filename)
        
        # Read the saved video file as byte array
        with open(video_filename, 'rb') as video_file:
            video_bytes = video_file.read()
            video_byte_array = list(video_bytes)
        
        video_data.append({
            'data': video_byte_array,
            'mediaType': 'video/mp4'
        })
        
        # Clean up the temporary file
        os.remove(video_filename)
        
        ai_logger.result(f"Video {n+1} processed and converted to byte array", agent_id, account_id, agent_name)

    if video_data:
        ai_logger.result(f"Successfully generated {len(video_data)} video(s) in MP4 format", agent_id, account_id, agent_name)
    else:
        ai_logger.warning("No video data was processed", agent_id, account_id, agent_name)
    
    # Return in the required format for Pancaik tools
    return {
        "values": {
            "output": {
                'media_data': video_data
            },
        },
    } 