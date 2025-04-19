"""
Template for creating new tools.

This module provides a template structure for adding new tools to the system.
"""

from datetime import datetime
from typing import Any, Dict

from ..core.config import logger
from ..core.data_handler import DataHandler
from ..tools.base import tool
from ..utils.ai_router import get_completion
from ..utils.json_parser import extract_json_content


@tool
async def template_tool_function(data_store: Dict[str, Any]):
    """
    Template for creating a new tool function.

    Provides a standard structure with common patterns and best practices for tool development.
    Replace this description with the specific purpose of your tool.

    Args:
        data_store: Agent's data store containing configuration, state, and context

    Returns:
        Dictionary with operation status and values to be shared in data_store
    """
    assert data_store, "Data store must be provided"

    # Get necessary configuration
    config = data_store.get("config", {})

    # Get agent_id, required for per-agent storage
    agent_id = data_store.get("agent_id")
    assert agent_id, "agent_id must be configured"

    # Get required input data from data_store
    input_data = data_store.get("input_key", {})
    assert input_data, "input_key must be available in data_store"

    # Get optional data if available
    optional_data = data_store.get("optional_key", {})

    # Get AI model for processing
    model_id = config.get("ai_models", {}).get("default")

    # Initialize database handler
    handler = DataHandler(collection_name="tool_data_collection")

    now = datetime.utcnow()
    today_date = now.strftime("%Y-%m-%d")

    # Check for cached data
    cache_key = f"tool_cache_{agent_id}_{today_date}"
    cached_data = await handler.get_data_by_key(cache_key)

    if cached_data:
        logger.info(f"Using cached data for agent {agent_id} dated {today_date}")
        return {"status": "success", "message": "Retrieved cached data", "values": {"result_key": cached_data.get("content", {})}}

    # Create prompt with XML structure
    prompt = f"""
    <task>
        Define the specific task for the AI model.
    </task>
    
    <context>
        Provide relevant context information.
        Date: {today_date}
        Input data: {input_data}
        {f"Additional context: {optional_data}" if optional_data else ""}
    </context>
    
    <instructions>
        1. First instruction for processing the data
        2. Second instruction with details
        3. Third instruction explaining the transformation
        4. Fourth instruction on evaluation criteria
        5. Final instruction about output formatting
    </instructions>
    
    <output_format>
        JSON with the following flat structure:
        {{
            "items": [
                "item1",
                "item2"
            ],
            "process_date": "{today_date}",
            "category": "main_category",
            "field1": "value1",
            "field2": "value2",
            "total_count": 0,
            "sources": ["source1", "source2"]
        }}
    </output_format>
    """

    try:
        # Get completion and extract JSON content
        response = await get_completion(prompt=prompt, model_id=model_id)
        processed_result = extract_json_content(response) or {}

        # Save the generated result to the database
        if await handler.save_data(cache_key, processed_result, now):
            logger.info(f"Successfully processed and saved data for agent {agent_id}")
            return {"status": "success", "message": "Data processed and saved successfully", "values": {"result_key": processed_result}}
        else:
            logger.error(f"Failed to save data for agent {agent_id}")
            return {"status": "error", "message": "Failed to save processed data", "values": {"result_key": processed_result}}
    except Exception as e:
        logger.error(f"Error during processing: {e}")
        return {"status": "error", "message": f"Processing failed: {str(e)}", "values": {}}
