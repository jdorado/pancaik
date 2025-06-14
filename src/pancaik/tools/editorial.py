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
    Selects a focused, unique topic and full background supporting information from a large context using LLM.
    This is intended for downstream content creation (e.g., articles, blogs, posts, or messages).
    The tool analyzes the input context and guidelines to produce a single, actionable topic and the key full background info to use for composing a piece.
    If no suitable topic can be found, it will gracefully exit the agent's pipeline.

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

    ai_logger.thinking(f"Analyzing context and guidelines for topic selection", agent_id, account_id, agent_name)
    logger.info(f"Running topic_selector for agent {agent_id} ({agent_name})")

    # --- Tool logic: LLM prompt for topic selection ---
    output_format = (
        '\nOUTPUT IN JSON: Strict JSON format, no additional text.\n'
        '"topic": "A single, unique, focused topic string. If no suitable topic is found, this should be an empty string.",\n'
        '"full_background": "Fully detailed background information from context to use for composing the piece. If no suitable topic is found, this should be an empty string.",\n'
        '"should_exit": "boolean, true if no unique or focused topic could be selected based on the guidelines, otherwise false."\n'
    )
    prompt_data = {
        "task": "From the provided context and selection guidelines, select a single, unique, and focused topic to discuss. Also, extract the most relevant full background information from the context that should be used for composing an article, blog, post, or message. The goal is to focus the content creation on this topic and supporting info. If no unique or focused topic can be selected, return true for should_exit.",
        "selection_guidelines": selection_guidelines,
        "context": data_store.get("context", {}),
        "output_format": output_format,
    }
    prompt = get_prompt(prompt_data, "topic_selector")
    model_id = config.get("ai_models", {}).get("default")

    response = await get_completion(prompt=prompt, model_id=model_id)
    parsed_response = extract_json_content(response) or {}

    if parsed_response.get("should_exit"):
        logger.info(f"topic_selector for agent {agent_id}: Gracefully exiting as no suitable topic was found.")
        return {"should_exit": True}

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
