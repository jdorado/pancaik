"""
Sample tool skeleton for Pancaik agents.

This module provides a template for creating new tools using the @tool decorator.

# - Tool is always async, no nested functions, keep it simple
# - Return {values: {context: {new_key: new_value}}} and use descriptive, globally-unique keys
# - Add 'should_exit': True to the return dict to gracefully end the pipeline when needed
# - Use a proper name to identify the output in a global context (avoid ambiguous names)
# - Do NOT use try/catch in the tool (the @tool decorator handles exceptions)
# - Follow the sample code pattern and keep code modular, clear, and open source quality
"""

from typing import Any, Dict

from ..core.config import logger
from ..utils.ai_router import get_completion
from ..utils.json_parser import extract_json_content
from ..utils.prompt_utils import get_prompt
from .base import tool


# Example: Register this tool for a specific agent by passing agents=["agent_example"]
@tool(agents=["agent_example"])
async def sample_tool(data_store: Dict[str, Any], param1: str, param2: int) -> Dict[str, Any]:
    """
    Sample tool that demonstrates the required structure for Pancaik tools, including both context and output.
    Also demonstrates using get_prompt and get_completion for LLM processing, including passing the full context from data_store.

    Args:
        data_store: Agent's data store containing configuration and state
        param1: Example string parameter
        param2: Example integer parameter

    Returns:
        Dictionary with operation status and values for context and output
    """
    # Preconditions (Design by Contract)
    assert data_store is not None, "data_store must be provided"
    assert isinstance(param1, str) and param1, "param1 must be a non-empty string"
    assert isinstance(param2, int), "param2 must be an integer"

    agent_id = data_store.get("agent_id")
    config = data_store.get("config", {})
    agent_name = config.get("name")
    logger.info(f"Running sample_tool for agent {agent_id} ({agent_name}) with param1={param1}, param2={param2}")

    # --- Tool logic: LLM prompt example ---
    output_format = """\nOUTPUT IN JSON: Strict JSON format, no additional text.\n"result": "Your result here"\n"""
    prompt_data = {
        "task": "Repeat the input string in uppercase N times.",
        "input_string": param1,
        "repeat_count": param2,
        "context": data_store.get("context", {}),
        "output_format": output_format,
    }
    prompt = get_prompt(prompt_data)
    model_id = config.get("ai_models", {}).get("default")
    response = await get_completion(prompt=prompt, model_id=model_id)

    # Parse the response as strict JSON
    parsed_response = extract_json_content(response) or {}

    context = {"llm_processed": parsed_response}

    # Postconditions (Design by Contract)
    assert "llm_processed" in context, "Context must contain 'llm_processed' key"

    # Return in the required format for Pancaik tools
    return {
        "values": {
            "context": context,
            "output": context,
        },
    }
