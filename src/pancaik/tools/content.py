from typing import Any, Dict

from ..core.ai_logger import ai_logger
from ..core.config import logger
from ..utils.ai_router import get_completion
from ..utils.prompt_utils import get_prompt
from .base import tool


@tool
async def text_composer(
    data_store: Dict[str, Any],
    content_prompt: str,
) -> Dict[str, Any]:
    """
    Composes a text item (blog, tweet, article, etc) based on the provided content_prompt.
    If topic_selection is present in context, it is referenced and followed strictly (and removed from context before LLM call).

    Args:
        data_store: Agent's data store containing configuration and state
        content_prompt: The prompt describing what to compose (e.g., instructions, style, type)

    Returns:
        Dictionary with operation status and values for context and output
    """
    # Preconditions (Design by Contract)
    assert data_store is not None, "data_store must be provided"
    assert isinstance(content_prompt, str) and content_prompt, "content_prompt must be a non-empty string"

    agent_id = data_store.get("agent_id")
    config = data_store.get("config", {})
    agent_name = config.get("name")
    account_id = config.get("account_id")

    logger.info(f"Running text_composer for agent {agent_id} ({agent_name}) with content_prompt: {content_prompt}")

    # Prepare context for prompt, extracting and removing topic_selection if present
    context = dict(data_store.get("context", {}))
    topic_selection = context.pop("topic_selection", None)
    # AI log: action
    ai_logger.action(
        "Composing text using LLM with provided context and prompt.",
        agent_id,
        account_id,
        agent_name,
    )

    # --- Tool logic: LLM prompt for composing text ---
    if topic_selection is not None:
        task = "Compose a text item based on the following instructions and adhere to the context. If topic_selection is present, follow it strictly."
    else:
        task = "Compose a text item based on the following instructions and adhere strictly to the context."
    prompt_data = {
        "task": task,
        "content_prompt": content_prompt,
    }
    if topic_selection is not None:
        prompt_data["topic_selection"] = topic_selection
    prompt_data["context"] = context

    prompt = get_prompt(prompt_data, "text_composer")
    model_id = config.get("ai_models", {}).get("composing")

    response = await get_completion(prompt=prompt, model_id=model_id)
    context = {"text_content": response}
    output = context

    # AI log: result
    ai_logger.result(
        f"Successfully composed text content of length {len(response)} characters",
        agent_id,
        account_id,
        agent_name,
    )

    return {
        "status": "success",
        "values": {
            "context": context,
            "output": output,
        },
    }
