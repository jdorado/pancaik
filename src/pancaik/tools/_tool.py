"""
Sample tool skeleton for Pancaik agents.

This module provides a template for creating new tools using the @tool decorator.

# Pancaik Tool Best Practices (@tools.mdc)
# - Return {values: {context: {new_key: new_value}}} and use descriptive, globally-unique keys
# - Add 'should_exit': True to the return dict to gracefully end the pipeline when needed
# - Use a proper name to identify the output in a global context (avoid ambiguous names)
# - Do NOT use try/catch in the tool (the @tool decorator handles exceptions)
# - Follow the sample code pattern and keep code modular, clear, and open source quality
"""

from typing import Any, Dict
from .base import tool
from ..core.config import logger
from ..utils.prompt_utils import get_prompt
from ..utils.ai_router import get_completion

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
    prompt_data = {
        "task": "Repeat the input string in uppercase N times.",
        "input_string": param1,
        "repeat_count": param2,
        "context": data_store.get("context", {}),
    }
    prompt = get_prompt(prompt_data)
    model_id = config.get("ai_models", {}).get("default") or "gpt-3.5-turbo"
    llm_result = await get_completion(prompt=prompt, model_id=model_id)

    context = {"llm_processed": llm_result}
    output = {"summary": f"LLM processed '{param1}' {param2} times"}

    # Postconditions (Design by Contract)
    assert "llm_processed" in context, "Context must contain 'llm_processed' key"
    assert "summary" in output, "Output must contain 'summary' key"

    # Return in the required format for Pancaik tools
    return {
        "status": "success",
        "values": {
            "context": context,
            "output": output,
        },
    }
