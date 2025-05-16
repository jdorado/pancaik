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
from .indexing import get_filtered_following_handles

@tool(agents=["agent_twitter_index_following"])
async def twitter_load_following_posts(
    twitter_connection: str,
    target_handle: str,
    data_store: dict,
    days_past: int = 7,
    followers_count: int = 100,
    include_replies: bool = False,
    analysis_mode: str = "default",
    criteria_for_analysis_selection: str = "",
):
    """
    Loads posts from users that a target user follows.

    Args:
        twitter_connection: Connection ID for Twitter credentials
        target_handle: The handle whose following list to load posts from
        days_past: Number of days in the past to look for posts
        data_store: Agent's data store containing configuration and state
        followers_count: Minimum number of followers required to include a user (default: 100)
        include_replies: Whether to include replies in the loaded posts (default: False)
        analysis_mode: Mode for analyzing posts (default: "default")
        criteria_for_analysis_selection: Optional criteria for analyzing posts

    Returns:
        Dictionary with loaded posts in 'values' for context update.
    """
    # Get filtered following handles
    usernames, metadata = await get_filtered_following_handles(
        twitter_connection=twitter_connection,
        target_handle=target_handle,
        data_store=data_store,
        min_followers=followers_count
    )
    
    if metadata["status"] != "success":
        return {
            "status": metadata["status"],
            "error": metadata.get("error", "Failed to get following handles"),
            "values": {}
        }

    # Convert usernames list to newline-separated string for twitter_load_past_posts
    target_handles = "\n".join(usernames)

    return await twitter_load_past_posts(
        target_handles=target_handles,
        days_past=days_past,
        data_store=data_store,
        include_replies=include_replies,
        analysis_mode=analysis_mode,
        criteria_for_analysis_selection=criteria_for_analysis_selection
    )


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
    
    # Load all posts in a single database query
    all_posts = await handler.get_tweets_from_users(
        usernames=handles,
        min_date=min_date,
        limit=1000  # Increased limit since we'll filter later
    )
    
    # Filter out replies if needed
    if not include_replies:
        all_posts = [
            post for post in all_posts 
            if not post.get("replied_to_id") and not post.get("inReplyToStatusId")
        ]

    # Sort posts by created_at date desc
    filtered_posts = sorted(all_posts, key=lambda x: x["created_at"], reverse=True)

    # Limit to last 100 posts
    filtered_posts = filtered_posts[:100]

    # Exit gracefully if no posts are found
    if not filtered_posts:
        ai_logger.error(
            f"No posts found for {handles} in the past {days_past} days",
            agent_id,
            account_id,
            agent_name,
        )
        return {
            "should_exit": True
        }

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
    model_id = config.get("ai_models", {}).get("mini")
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
