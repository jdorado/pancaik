"""
Tool for selecting and interacting with Twitter posts.

This module provides functionality to prepare and execute different types of Twitter interactions
(repost, quote, reply) with selected posts based on specified criteria.
"""

from typing import Any, Dict, List

from ...core.config import logger, get_config
from ...utils.ai_router import get_completion
from ...utils.json_parser import extract_json_content
from ...utils.prompt_utils import get_prompt
from ...tools.base import tool
from ...core.connections import ConnectionHandler
from ...core.ai_logger import ai_logger
from . import client as twitter_client
from .handlers import TwitterHandler


@tool()
async def twitter_select_and_interact(
    data_store: Dict[str, Any],
    twitter_connection: str,
    interaction_types: List[str],
    twitter_posts: List[Dict[str, Any]],
    selection_criteria: str,
    min_days_between_user_interactions: int = 3,
) -> Dict[str, Any]:
    """
    Selects Twitter posts based on criteria and prepares specified interaction types.

    Args:
        data_store: Agent's data store containing configuration and state
        twitter_connection: Twitter connection identifier
        interaction_types: List of interaction types to prepare ('repost', 'quote', 'reply')
        twitter_posts: List of Twitter posts to analyze and select from
        selection_criteria: Criteria for selecting which posts to interact with
        min_days_between_user_interactions: Minimum days to wait before interacting with the same user again

    Returns:
        Dictionary with operation status and values for context and output containing:
        - Selected posts
        - Prepared interactions for each selected post
    """
    # Preconditions (Design by Contract)
    assert data_store is not None, "data_store must be provided"
    assert twitter_connection, "twitter_connection must be provided"
    assert isinstance(interaction_types, list) and interaction_types, "interaction_types must be a non-empty list"
    assert all(t in ['repost', 'quote', 'reply'] for t in interaction_types), "Invalid interaction type provided"
    assert isinstance(twitter_posts, list) and twitter_posts, "twitter_posts must be a non-empty list"
    assert isinstance(selection_criteria, str) and selection_criteria.strip(), "selection_criteria must be a non-empty string"

    agent_id = data_store.get("agent_id")
    config = data_store.get("config", {})
    agent_name = config.get("name")
    account_id = config.get("account_id")
    logger.info(f"Running twitter_select_and_interact for agent {agent_id} ({agent_name})")
    
    ai_logger.thinking(
        f"Starting Twitter post selection with criteria: {selection_criteria}. "
        f"Looking for {', '.join(interaction_types)} opportunities.",
        agent_id, account_id, agent_name
    )

    # Initialize Twitter client
    db = get_config("db")
    if db is None:
        raise ValueError("Database not initialized in config")

    connection_handler = ConnectionHandler(db)
    twitter = await twitter_client.get_client(twitter_connection, connection_handler)

    # Filter out RT
    twitter_posts = [post for post in twitter_posts if not post.get("text", "").startswith("RT")]

    # Filter posts we have already interacted or analyzed
    twitter_handler = TwitterHandler()
    username = twitter.get_username()
    
    # Get post IDs to check
    post_ids = [post["_id"] for post in twitter_posts]
    
    ai_logger.action(
        f"Filtering {len(post_ids)} posts for previous interactions by {username}",
        agent_id, account_id, agent_name
    )
    
    # Get IDs of posts we've already interacted with
    processed_post_ids = await twitter_handler.get_posts_with_interactions(
        post_ids=post_ids,
        username=username
    )
    
    # Filter out posts we've already processed
    twitter_posts = [post for post in twitter_posts if post["_id"] not in processed_post_ids]
    
    if not twitter_posts:
        ai_logger.result(
            "All provided posts have already been processed - no action needed",
            agent_id, account_id, agent_name
        )
        return {
            "should_exit": True
        }
    
    # Get unique usernames from remaining posts
    usernames = list(set(post.get("username") for post in twitter_posts if post.get("username")))
    
    ai_logger.action(
        f"Checking interaction history with {len(usernames)} users",
        agent_id, account_id, agent_name
    )
    
    # Get last interaction dates for these usernames
    last_interactions = await twitter_handler.get_last_interactions_by_usernames(
        usernames=usernames,
        username=username
    )
    
    # Filter out posts from users we've interacted with recently
    from datetime import datetime, timedelta
    current_time = datetime.utcnow()
    cooling_period = timedelta(days=int(min_days_between_user_interactions))
    
    filtered_posts = []
    for post in twitter_posts:
        post_username = post.get("username")
        if not post_username:
            continue
            
        last_interaction = last_interactions.get(post_username)
        if not last_interaction:
            filtered_posts.append(post)
            continue
            
        time_since_last = current_time - last_interaction
        if time_since_last >= cooling_period:
            filtered_posts.append(post)
    
    twitter_posts = filtered_posts
    
    if not twitter_posts:
        ai_logger.result(
            "All posts filtered out due to recent interactions with users",
            agent_id, account_id, agent_name
        )
        return {
            "should_exit": True
        }

    # TODO limit number per LLM call / do loop until one
    twitter_posts = twitter_posts[:1] # TODO tmp

    ai_logger.thinking(
        f"Analyzing {len(twitter_posts)} posts against selection criteria",
        agent_id, account_id, agent_name
    )

    # --- Tool logic: LLM prompt example ---
    output_format = """\nOUTPUT IN JSON: Strict JSON format, no additional text.
    {
        "posts": [
            {
                "post_id": "string",
                "selection_rationale": "string",
                "match_score": "number",
                "interaction_type": "string",
            }
        ]
    }
    """
    
    # Add 'ignore' to the valid interaction types
    valid_actions = interaction_types + ['ignore']
    action_list = ", ".join(valid_actions)
    
    prompt_data = {
        "task": f"Analyze the following Twitter posts and decide your action from these options: {action_list}.\n For each post, provide a rationale for your decision. Determine the match score (1-100, 100 being the best match) for each post based on the selection criteria and context.",
        "selection_criteria": selection_criteria,
        "twitter_posts": [{"_id": post["_id"], "text": post["text"]} for post in twitter_posts],
        "context": data_store.get("context", {}),
        "output_format": output_format,
    }
    prompt = get_prompt(prompt_data, "twitter_select_and_interact")
    model_id = config.get("ai_models", {}).get("mini")
    response = await get_completion(prompt=prompt, model_id=model_id)

    # Parse the response as strict JSON
    parsed_response = extract_json_content(response) or {}
    posts = parsed_response.get("posts", [])

    # Get the top ranked tweet based on match_score
    top_tweet = None
    if posts:
        # Check if all posts are marked as 'ignore'
        if all(post.get("interaction_type") == "ignore" for post in posts):
            ai_logger.result(
                "All posts marked for ignoring - no suitable interactions found",
                agent_id, account_id, agent_name
            )
            return {
                "should_exit": True
            }
            
        top_tweet = max(posts, key=lambda x: float(x.get("match_score", 0)))
        ai_logger.result(
            f"Selected post with match score {top_tweet.get('match_score')} "
            f"for {top_tweet.get('interaction_type')} interaction. "
            f"Rationale: {top_tweet.get('selection_rationale')}",
            agent_id, account_id, agent_name
        )

    # Mark posts with their respective interactions in the database
    for post in posts:
        post_id = post.get("post_id")
        interaction_type = post.get("interaction_type")
        
        if post_id and interaction_type:
            # Map interaction types to database values
            interaction_map = {
                'ignore': 'ignored',
                'reply': 'replied',
                'quote': 'quoted',
                'repost': 'retweeted'
            }
            
            db_interaction_type = interaction_map.get(interaction_type)
            if db_interaction_type:
                # Mark the post with the appropriate interaction type
                success = await twitter_handler.mark_post_interaction(
                    post_id=post_id,
                    username=username,
                    interaction_type=db_interaction_type
                )
                if success:
                    logger.info(f"Marked post {post_id} as {db_interaction_type}")
                else:
                    logger.warning(f"Failed to mark post {post_id} as {db_interaction_type}")

    # Find the full tweet object for the top ranked tweet
    selected_tweet = next(
        (post for post in twitter_posts if post["_id"] == top_tweet["post_id"]),
        None
    )

    outputs = {
        "selected_tweet": selected_tweet,
        "interaction_type": top_tweet["interaction_type"]
    }

    # Set tweet composing instructions based on interaction type
    if top_tweet["interaction_type"] == "reply":
        tweet_composing_instructions = f"Reply to {selected_tweet['username']}'s tweet. Keep it conversational and engaging."
    elif top_tweet["interaction_type"] == "quote":
        tweet_composing_instructions = f"Quote {selected_tweet['username']}'s tweet with your own perspective."
    elif top_tweet["interaction_type"] == "repost":
        tweet_composing_instructions = ""

    context = {
        "selected_tweet": f"{selected_tweet['text']}" if selected_tweet else None,
        'tweet_composing_instructions': tweet_composing_instructions,
    }

    # Postconditions (Design by Contract)
    assert isinstance(context, dict), "context must be a dictionary"
    assert "selected_tweet" in context, "context must contain 'selected_tweet' key"
    assert isinstance(context["selected_tweet"], (str, type(None))), "context selected_tweet must be a string or None"
    assert "selected_tweet" in outputs, "output must contain 'selected_tweet' key"
    assert "interaction_type" in outputs, "output must contain 'interaction_type' key"

    ai_logger.action(
        f"Preparing {top_tweet['interaction_type']} interaction with selected tweet",
        agent_id, account_id, agent_name
    )

    # Return in the required format for Pancaik tools
    return {
        "values": {
            "context": context,
            "output": outputs,
            "delete_context": ['twitter_posts']
        },
    }
