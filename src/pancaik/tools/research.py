"""
Research tools for agents.

This module provides tools for generating and managing research content.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from ..core.ai_logger import ai_logger
from ..tools.base import tool
from ..utils.ai_router import get_completion
from ..utils.prompt_utils import get_prompt


@tool
async def research(
    research_prompt: str, 
    research_model: str, 
    data_store: Dict[str, Any], 
    topic_selection: Optional[Dict[str, str]] = None,
    context_selection: Optional[str] = None,
    reset_context: bool = True
):
    """
    Performs research using Perplexity.

    Args:
        research_prompt: The research prompt to process
        research_model: The model ID to use for research
        data_store: Agent's data store containing configuration and state
        topic_selection: Optional dictionary containing 'topic' and 'distilled_info' for pre-selected research topics
        context_selection: Optional string to determine context inclusion strategy. 
                           If 'full_context', includes both data_store context and topic_selection.
                           If 'topic_selector_only', includes only topic_selection.
        reset_context: If True, previous context will be reset and the research output will become 
                       the new context for the agent. Default is True.

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
        "research_prompt": research_prompt,
    }
    
    # Handle context based on context_selection parameter
    if context_selection == "full_context":
        prompt_data["context"] = data_store.get("context", {})
        # Add topic selection if provided
        if topic_selection and isinstance(topic_selection, dict):
            if "topic" in topic_selection and "distilled_info" in topic_selection:
                prompt_data["topic_selection"] = topic_selection
                ai_logger.thinking(
                    f"Using pre-selected topic with full context: {topic_selection['topic']}",
                    agent_id=agent_id,
                    account_id=account_id,
                    agent_name=agent_name
                )
    elif context_selection == "topic_selector_only":
        # Ensure topic_selection is not None when using topic_selector_only
        assert topic_selection is not None, "topic_selection must be provided when context_selection is 'topic_selector_only'"
        assert isinstance(topic_selection, dict), "topic_selection must be a dictionary"
        assert "topic" in topic_selection and "distilled_info" in topic_selection, "topic_selection must contain 'topic' and 'distilled_info' keys"
        
        prompt_data["topic_selection"] = topic_selection
        ai_logger.thinking(
            f"Using only pre-selected topic: {topic_selection['topic']}",
            agent_id=agent_id,
            account_id=account_id,
            agent_name=agent_name
        )
    else:
        # Default behavior - include data_store context
        prompt_data["context"] = data_store.get("context", {})
        
        # Add topic selection if provided
        if topic_selection and isinstance(topic_selection, dict):
            if "topic" in topic_selection and "distilled_info" in topic_selection:
                prompt_data["topic_selection"] = topic_selection
                ai_logger.thinking(
                    f"Using pre-selected topic: {topic_selection['topic']}",
                    agent_id=agent_id,
                    account_id=account_id,
                    agent_name=agent_name
                )
    
    prompt = get_prompt(prompt_data)

    ai_logger.action(f"Querying Perplexity with formatted prompt", agent_id=agent_id, account_id=account_id, agent_name=agent_name)
    research_result = await get_completion(prompt=prompt, model_id=research_model)

    ai_logger.result(
        f"Research completed successfully. Generated {len(research_result)} characters of insights",
        agent_id=agent_id,
        account_id=account_id,
        agent_name=agent_name,
    )
    
    # Create new context with research result
    context = {"research": research_result}
    
    # Prepare return values
    return_values = {"context": context, "output": context}
    
    # Handle context reset logic using the delete_context mechanism
    if reset_context:
        ai_logger.thinking(
            "Resetting previous context and using new research output as context",
            agent_id=agent_id,
            account_id=account_id,
            agent_name=agent_name
        )
        
        # Get all existing context keys to delete
        existing_context_keys = list(data_store.get("context", {}).keys())
        if existing_context_keys:
            return_values["delete_context"] = existing_context_keys

    return {
        "status": "success",
        "message": "Perplexity research completed",
        "values": return_values,
    }
