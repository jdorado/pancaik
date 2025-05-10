"""
Twitter post loading tools for agents.

This module provides tools for loading and analyzing tweets from users.
"""

from datetime import datetime, timedelta
from json import tool

from ...core.ai_logger import ai_logger
from ...tools.base import tool
from ...utils.ai_router import get_completion
from ...utils.json_parser import extract_json_content
from ...utils.prompt_utils import get_prompt
from .handlers import TwitterHandler


@tool(agents=["agent_twitter_index_user"])
async def twitter_load_past_posts(
    target_handle: str,
    days_past: int,
    data_store: dict,
    include_replies: bool = False,
    analysis_mode: str = "default",
    criteria_for_analysis_selection: str = "",
):
    """
    Loads previous Twitter posts for a user based on parameters.

    Args:
        target_handle: The handle of the user to load posts for.
        days_past: Number of days in the past to look for posts.
        content_guidelines: Optional guidelines for analyzing posts.
        data_store: Agent's data store containing configuration and state.
        include_replies: Whether to include replies in the loaded posts (default: False).

    Returns:
        Dictionary with loaded posts in 'values' for context update.
    """
    assert days_past is not None, "'days_past' must be provided"
    assert data_store is not None, "data_store must be provided"
    assert isinstance(include_replies, bool), "include_replies must be a boolean"
    agent_id = data_store.get("agent_id")
    config = data_store.get("config", {})
    account_id = config.get("account_id")
    agent_name = config.get("name")
    ai_logger.thinking(
        f"Loading past Twitter posts for {target_handle} (days_past={days_past}, include_replies={include_replies}, analysis_mode={analysis_mode})",
        agent_id,
        account_id,
        agent_name,
    )
    min_date = datetime.utcnow() - timedelta(days=int(days_past))
    handler = TwitterHandler()
    ai_logger.action(f"Fetching tweets for {target_handle} from TwitterHandler", agent_id, account_id, agent_name)
    posts = await handler.get_tweets_by_user(target_handle, limit=1000, include_replies=include_replies)
    # Filter posts by min_date
    filtered_posts = [post for post in posts if post.get("created_at") and post["created_at"] >= min_date]
    # Limit to last 100 posts
    filtered_posts = filtered_posts[-100:]
    # Flatten posts into list of strings
    posts_text = [post.get("text", "") for post in filtered_posts]
    context = {}
    output = {}
    model_id = config.get("ai_models", {}).get("default")
    if analysis_mode == "default":
        context = {f"{target_handle}_twitter_posts": posts_text}
        ai_logger.result(f"Loaded {len(posts_text)} posts for {target_handle} (default mode)", agent_id, account_id, agent_name)
    elif analysis_mode == "summarize_analyze":
        prompt_data = {
            "task": "Summarize and analyze the following Twitter posts.",
            "summary_analysis_criteria": criteria_for_analysis_selection,
            "posts": posts_text,
            "context": data_store.get("context", {}),
        }
        prompt = get_prompt(prompt_data, "twitter_analysis_request")
        ai_logger.action(f"Requesting LLM summary/analysis for {target_handle}", agent_id, account_id, agent_name)
        response = await get_completion(prompt=prompt, model_id=model_id)
        context = {f"{target_handle}_twitter_posts_summary": response}
        output = {f"{target_handle}_twitter_posts_summary": response}
        ai_logger.result(f"Received summary/analysis for {target_handle}", agent_id, account_id, agent_name)
    elif analysis_mode == "filter_criteria":
        output_format = (
            """\nOUTPUT IN JSON: Strict JSON format, no additional text.\n"filtered_posts": [{{"text": "...", "reason": "..."}}]\n"""
        )
        prompt_data = {
            "task": "Filter the following Twitter posts according to the criteria. For each post that matches, include a reason.",
            "filter_criteria": criteria_for_analysis_selection,
            "posts": posts_text,
            "context": data_store.get("context", {}),
            "output_format": output_format,
        }
        prompt = get_prompt(prompt_data, "twitter_filter_request")
        ai_logger.action(f"Requesting LLM filter for {target_handle} with criteria", agent_id, account_id, agent_name)
        response = await get_completion(prompt=prompt, model_id=model_id)
        parsed_response = extract_json_content(response) or {}
        parsed_response["filtered_posts"] = [post.get("text", "") for post in parsed_response.get("filtered_posts", [])]
        context = {f"{target_handle}_twitter_posts": parsed_response.get("filtered_posts", [])}
        ai_logger.result(f"Filtered posts for {target_handle} using criteria", agent_id, account_id, agent_name)
    return {
        "status": "success",
        "values": {
            "context": context,
            "output": output,
        },
    }
