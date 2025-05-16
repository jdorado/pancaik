"""
Twitter post loading tools for agents.

This module provides tools for loading and analyzing tweets from users.
"""

from datetime import datetime, timedelta
from json import tool
from typing import Union, List

from ...core.ai_logger import ai_logger
from ...tools.base import tool
from ...utils.ai_router import get_completion
from ...utils.json_parser import extract_json_content
from ...utils.prompt_utils import get_prompt
from .handlers import TwitterHandler


@tool(agents=["agent_twitter_index_user"])
async def twitter_load_past_posts(
    target_handles: str,
    days_past: int,
    data_store: dict,
    include_replies: bool = False,
    analysis_mode: str = "default",
    criteria_for_analysis_selection: str = "",
):
    """
    Loads previous Twitter posts for one or more users based on parameters.

    Args:
        target_handles: The handle(s) of the user(s) to load posts for. Can be a single handle or multiple handles separated by newlines.
                      Handles can optionally include @ symbol which will be removed.
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
    assert isinstance(target_handles, str), "target_handles must be a string"
    
    # Split handles by newlines, remove @ symbols, and filter out empty strings
    handles = [h.strip().lstrip('@') for h in target_handles.split('\n') if h.strip()]
    
    agent_id = data_store.get("agent_id")
    config = data_store.get("config", {})
    account_id = config.get("account_id")
    agent_name = config.get("name")
    
    ai_logger.thinking(
        f"Loading past Twitter posts for {handles} (days_past={days_past}, include_replies={include_replies}, analysis_mode={analysis_mode})",
        agent_id,
        account_id,
        agent_name,
    )
    
    min_date = datetime.utcnow() - timedelta(days=int(days_past))
    handler = TwitterHandler()
    
    all_posts = []
    for handle in handles:
        ai_logger.action(f"Fetching tweets for {handle} from TwitterHandler", agent_id, account_id, agent_name)
        posts = await handler.get_tweets_by_user(handle, limit=1000, include_replies=include_replies)
        all_posts.extend(posts)
    
    # Filter posts by min_date
    filtered_posts = [post for post in all_posts if post.get("created_at") and post["created_at"] >= min_date]

    # Sort posts by created_at date desc
    filtered_posts = sorted(filtered_posts, key=lambda x: x["created_at"], reverse=True)

    # Limit to last 100 posts
    filtered_posts = filtered_posts[-100:]
    # Flatten posts into list of strings
    posts_text = [post.get("text", "") for post in filtered_posts]
    # Create selective output format
    selective_posts = [
        {
            "_id": post.get("_id"),
            "username": post.get("username"),
            "text": post.get("text")
        }
        for post in filtered_posts
    ]
    context = {}
    output = {}
    model_id = config.get("ai_models", {}).get("default")
    if analysis_mode == "default":
        context = {"twitter_posts": posts_text}
        output = {"twitter_posts": selective_posts}
        ai_logger.result(f"Loaded {len(posts_text)} posts for {handles} (default mode)", agent_id, account_id, agent_name)
    elif analysis_mode == "summarize_analyze":
        prompt_data = {
            "task": "Summarize and analyze the following Twitter posts.",
            "summary_analysis_criteria": criteria_for_analysis_selection,
            "posts": posts_text,
            "context": data_store.get("context", {}),
        }
        prompt = get_prompt(prompt_data, "twitter_analysis_request")
        ai_logger.action(f"Requesting LLM summary/analysis for {handles}", agent_id, account_id, agent_name)
        response = await get_completion(prompt=prompt, model_id=model_id)
        context = {"posts_summary": response}
        output = {"posts_summary": response}
        ai_logger.result(f"Received summary/analysis for {handles}", agent_id, account_id, agent_name)
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
        ai_logger.action(f"Requesting LLM filter for {handles} with criteria", agent_id, account_id, agent_name)
        response = await get_completion(prompt=prompt, model_id=model_id)
        parsed_response = extract_json_content(response) or {}
        filtered_post_texts = [post.get("text", "") for post in parsed_response.get("filtered_posts", [])]
        filtered_full_posts = [
            {
                "_id": post.get("_id"),
                "username": post.get("username"),
                "text": post.get("text")
            }
            for post in filtered_posts if post.get("text") in filtered_post_texts
        ]
        context = {"twitter_posts": filtered_post_texts}
        output = {"twitter_posts": filtered_full_posts}
        ai_logger.result(f"Filtered posts for {handles} using criteria", agent_id, account_id, agent_name)
    return {
        "status": "success",
        "values": {
            "context": context,
            "output": output,
        },
    }
