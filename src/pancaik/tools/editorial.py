from typing import Any, Dict

from ..core.ai_logger import ai_logger
from ..core.config import logger
from ..utils.ai_router import get_completion
from ..utils.json_parser import extract_json_content
from ..utils.prompt_utils import get_prompt
from .base import tool


@tool
async def topic_selector(data_store: Dict[str, Any], selection_guidelines: str) -> Dict[str, Any]:
    """
    Selects a focused, unique topic and distilled supporting information from a large context using LLM.
    This is intended for downstream content creation (e.g., articles, blogs, posts, or messages).
    The tool analyzes the input context and guidelines to produce a single, actionable topic and the key distilled info to use for composing a piece.

    Args:
        data_store: Agent's data store containing configuration and state
        selection_guidelines: String with rules or criteria for topic selection

    Returns:
        Dictionary with operation status and values for context and output
    """
    # Preconditions (Design by Contract)
    assert data_store is not None, "data_store must be provided"
    assert isinstance(selection_guidelines, str) and selection_guidelines, "selection_guidelines must be a non-empty string"

    agent_id = data_store.get("agent_id")
    config = data_store.get("config", {})
    account_id = config.get("account_id")
    agent_name = config.get("name")

    ai_logger.thinking(
        f"Analyzing context and guidelines for topic selection", agent_id, account_id, agent_name
    )
    logger.info(f"Running topic_selector for agent {agent_id} ({agent_name}) with guidelines: {selection_guidelines}")

    # --- Tool logic: LLM prompt for topic selection ---
    output_format = (
        "\nOUTPUT IN JSON: Strict JSON format, no additional text.\n"
        '"topic": "A single, unique, focused topic string",\n'
        '"distilled_info": "Key distilled information from context to use for composing the piece"\n'
    )
    prompt_data = {
        "task": "From the provided context and selection guidelines, select a single, unique, and focused topic to discuss. Also, extract the most relevant distilled information from the context that should be used for composing an article, blog, post, or message. The goal is to focus the content creation on this topic and supporting info.",
        "selection_guidelines": selection_guidelines,
        "context": data_store.get("context", {}),
        "output_format": output_format,
    }
    prompt = get_prompt(prompt_data, "topic_selector")
    model_id = config.get("ai_models", {}).get("default")

    response = await get_completion(prompt=prompt, model_id=model_id)
    parsed_response = extract_json_content(response) or {}
    context = {"topic_selection": parsed_response}
    output = context

    # Postconditions (Design by Contract)
    assert "topic_selection" in context, "Context must contain 'topic_selection' key"

    return {
        "status": "success",
        "values": {
            "context": context,
            "output": output,
        },
    }
