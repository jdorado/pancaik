"""
Research tools for agents.

This module provides tools for generating and managing research content.
"""

from datetime import datetime
from typing import Any, Dict

from ..core.ai_logger import ai_logger
from ..tools.base import tool
from ..utils.ai_router import get_completion
from ..utils.prompt_utils import get_prompt


@tool
async def research_perplexity(research_prompt: str, research_model: str, data_store: Dict[str, Any]):
    """
    Performs research using Perplexity.

    Args:
        research_prompt: The research prompt to process
        research_model: The model ID to use for research
        data_store: Agent's data store containing configuration and state

    Returns:
        Dictionary containing operation status and research results in values
    """
    assert research_prompt, "Research prompt must be provided"
    assert research_model, "Research model must be provided"
    assert data_store, "Data store must be provided"

    agent_id = data_store.get("agent_id")
    config = data_store.get("config", {})
    account_id = config.get("account_id")
    agent_name = config.get("name")
    assert account_id, "account_id must be provided in data_store config"

    today_date = datetime.utcnow().strftime("%Y-%m-%d")

    ai_logger.thinking(f"Starting research on: {research_prompt[:100]}...", agent_id=agent_id, account_id=account_id, agent_name=agent_name)

    # Format the prompt using XML style with nested context
    prompt_data = {
        "date": today_date,
        "task": "Conduct detailed and comprehensive research on the following research prompt.",
        "context": data_store.get("context", {}),
        "research_prompt": research_prompt,
    }
    prompt = get_prompt(prompt_data)

    ai_logger.action(f"Querying Perplexity with formatted prompt", agent_id=agent_id, account_id=account_id, agent_name=agent_name)
    research_result = await get_completion(prompt=prompt, model_id=research_model)

    ai_logger.result(
        f"Research completed successfully. Generated {len(research_result)} characters of insights",
        agent_id=agent_id,
        account_id=account_id,
        agent_name=agent_name,
    )

    return {
        "status": "success",
        "message": "Perplexity research completed",
        "values": {"context": {"research": research_result}, "output": {"latest_research": research_result}},
    }
