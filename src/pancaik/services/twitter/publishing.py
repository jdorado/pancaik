"""
Twitter publishing tools for agents.

This module provides tools for composing and publishing tweets.
"""

from typing import Any, Dict, Optional
from datetime import datetime
from tweepy.errors import TweepyException

from ...core.ai_logger import ai_logger
from ...core.config import get_config, logger
from ...core.connections import ConnectionHandler
from ...tools.base import tool
from . import client, indexing
from .client import TwitterClient
from .handlers import TwitterHandler


@tool()
async def twitter_publish_post(
    twitter_connection: str,
    text_content: str = None,
    data_store: Optional[Dict[str, Any]] = None,
    selected_tweet: Optional[Dict[str, Any]] = None,
    interaction_type: Optional[str] = None,
    media_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Publish a tweet to Twitter.

    Args:
        twitter_connection: Connection ID for Twitter credentials
        text_content: Content for the tweet
        data_store: Optional data store for additional context
        selected_tweet: Optional dictionary containing tweet data for interactions/replies
        interaction_type: Optional string specifying type of interaction (e.g. reply, quote, retweet)
        media_data: Optional media data to attach to the tweet

    Returns:
        Dictionary with publishing operation results
    """
    # Preconditions
    assert (
        text_content or media_data or (interaction_type == "repost" and selected_tweet)
    ), "Tweet content or media must be provided unless retweeting"

    # Extract AI logging context
    agent_id = data_store.get("agent_id") if data_store else None
    account_id = data_store.get("config", {}).get("account_id") if data_store else None
    agent_name = data_store.get("config", {}).get("name") if data_store else None

    # Get database instance from config
    db = get_config("db")
    if db is None:
        raise ValueError("Database not initialized in config")

    # Initialize connection handler with db
    connection_handler = ConnectionHandler(db)
    twitter: TwitterClient = await client.get_client(twitter_connection, connection_handler)

    # Get the semaphore for Twitter API rate limiting
    semaphore = get_config("twitter_semaphore")
    assert semaphore is not None, "Twitter semaphore must be available in config"

    # Prepare tweet parameters based on interaction type
    tweet_params = {"text": text_content or ""}

    # Add media data if provided
    if media_data is not None:
        tweet_params["media_data"] = media_data

    if selected_tweet and interaction_type:
        tweet_id = selected_tweet.get("_id")
        if interaction_type == "reply":
            tweet_params["reply_id"] = tweet_id
        elif interaction_type == "quote":
            tweet_params["quote_id"] = tweet_id
        elif interaction_type == "repost":
            # For repost, we don't need text content
            tweet_params = {"text": "", "quote_id": tweet_id}
            # Re-add media data for reposts if provided
            if media_data is not None:
                tweet_params["media_data"] = media_data

    # Publish the tweet
    ai_logger.action(f"Publishing tweet{f' as {interaction_type}' if interaction_type else ''}.", agent_id, account_id, agent_name)

    # Check rate limit status before attempting to publish
    rate_limit_check = await twitter.is_rate_limit_exceeded()
    if rate_limit_check["exceeded"]:
        wait_minutes = rate_limit_check["retry_after_minutes"]
        error_msg = f"Rate limit exceeded for tweet creation. Limit resets in {wait_minutes} minutes."
        logger.warning(error_msg)
        ai_logger.error(error_msg, agent_id, account_id, agent_name)
        return {"processing": True, "process_minutes": wait_minutes, "resume_from_step": 0, "message": error_msg}

    # Acquire semaphore to respect rate limits
    await semaphore.acquire()
    try:
        tweet = await twitter.create_tweet(**tweet_params)
    except TweepyException as e:
        error_msg = f"Tweet creation failed: {e}"
        logger.error(error_msg)
        ai_logger.error(error_msg, agent_id, account_id, agent_name)
        
        if "TooManyRequests" in str(e):
            wait_minutes = 15  # Default wait time
            rate_limit_error_msg = f"Rate limit exceeded for tweet creation. Retrying in {wait_minutes} minutes."
            logger.warning(rate_limit_error_msg)
            ai_logger.error(rate_limit_error_msg, agent_id, account_id, agent_name)
            return {"processing": True, "process_minutes": wait_minutes, "resume_from_step": 0, "message": rate_limit_error_msg}

        raise RuntimeError(error_msg)
    finally:
        # Always release the semaphore
        semaphore.release()

    if "id" not in tweet:
        error_msg = "Invalid tweet response format"
        logger.error(error_msg)
        ai_logger.error(error_msg, agent_id, account_id, agent_name)
        raise ValueError(f"{error_msg}: Missing tweet ID in response")
    tweet_id = tweet["id"]

    # Index the tweet
    username = twitter.get_username()
    await indexing.twitter_index_by_id(twitter_connection=twitter_connection, tweet_id=tweet_id, data_store=data_store)

    # Mark interaction in database if we have an interaction type
    if interaction_type and selected_tweet:
        twitter_handler = TwitterHandler()
        username = twitter.get_username()

        # Map interaction types to database values
        interaction_map = {"reply": "replied", "quote": "quoted", "repost": "retweeted"}

        db_interaction_type = interaction_map.get(interaction_type)
        if db_interaction_type:
            post_id = selected_tweet.get("_id")
            success = await twitter_handler.mark_post_interaction(post_id=post_id, username=username, interaction_type=db_interaction_type)
            if success:
                logger.info(f"Marked post {post_id} as {db_interaction_type}")
            else:
                logger.warning(f"Failed to mark post {post_id} as {db_interaction_type}")

    # Postcondition - ensure we have the publishing results
    result = {
        "status": "success",
        "values": {
            "output": {
                "tweet": {
                    "text": text_content or "",
                    "url": f"https://x.com/{username}/status/{tweet_id}",
                    "interaction_type": interaction_type if interaction_type else None,
                    "interaction_with": selected_tweet.get("_id") if selected_tweet else None,
                },
            },
        },
    }

    ai_logger.result(
        f"Successfully published tweet{f' as {interaction_type}' if interaction_type else ''}", agent_id, account_id, agent_name
    )
    return result
