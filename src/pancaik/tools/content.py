import base64
from typing import Any, Dict

from ..core.ai_logger import ai_logger
from ..core.config import logger
from ..utils.ai_router import compose_multimodal_prompt, get_completion
from ..utils.json_parser import extract_json_content
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

    logger.info(f"Running text_composer for agent {agent_id} ({agent_name}) with content_prompt")

    # Prepare context for prompt, extracting and removing topic_selection if present
    context = dict(data_store.get("context", {}))
    topic_selection = context.pop("topic_selection", None)
    media_context = context.pop("media_context", None)
    # AI log: action
    ai_logger.action(
        "Composing text using LLM with provided context and prompt.",
        agent_id,
        account_id,
        agent_name,
    )

    # --- Tool logic: LLM prompt for composing text ---
    output_format = """\nOUTPUT IN JSON: Strict JSON format, no additional text.\n"text_content": "Your composed text content here"\n"""

    if topic_selection is not None:
        task = "Compose a text item based on the following instructions and adhere to the context. If topic_selection is present, follow it strictly."
    else:
        task = "Compose a text item based on the following instructions and adhere strictly to the context."
    prompt_data = {
        "task": task,
        "content_prompt": content_prompt,
        "output_format": output_format,
    }
    if topic_selection is not None:
        prompt_data["topic_selection"] = topic_selection
    prompt_data["context"] = context

    text_prompt = get_prompt(prompt_data, "text_composer")
    model_id = config.get("ai_models", {}).get("composing")

    final_prompt: Any = text_prompt
    if media_context:
        ai_logger.action(
            f"Found {len(media_context)} media items. Preparing multimodal prompt.",
            agent_id,
            account_id,
            agent_name,
        )
        images_base64 = []
        for media_item in media_context:
            image_bytes = bytes(media_item.get("data", []))
            if image_bytes:
                images_base64.append(base64.b64encode(image_bytes).decode("utf-8"))

        if images_base64:
            image_format = media_context[0].get("mediaType", "image/jpeg").split("/")[-1]
            final_prompt = compose_multimodal_prompt(text=text_prompt, images=images_base64, image_format=image_format)
            model_id = config.get("ai_models", {}).get("vision", model_id)

    response = await get_completion(prompt=final_prompt, model_id=model_id)

    # Parse the response as strict JSON
    parsed_response = extract_json_content(response) or {}
    text_content = parsed_response.get("text_content", response)  # Fallback to raw response if parsing fails

    context = {"text_content": text_content}
    output = context

    # AI log: result
    ai_logger.result(
        f"Successfully composed text content of length {len(text_content)} characters",
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
