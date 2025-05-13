"""
Twitter publishing tools for agents.

This module provides tools for composing and publishing tweets.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from ...core.ai_logger import ai_logger
from ...core.config import get_config, logger
from ...core.connections import ConnectionHandler
from ...tools.base import tool
from . import client, indexing
from .client import TwitterClient
from .handlers import TwitterHandler


@tool()
async def twitter_publish_post(
    twitter_connection: str, text_content: str = None, data_store: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Publish a tweet to Twitter.

    Args:
        twitter_connection: Connection ID for Twitter credentials
        text_content: Content for the tweet
        data_store: Optional data store for additional context

    Returns:
        Dictionary with publishing operation results
    """
    # Preconditions
    assert text_content, "Tweet content must be provided"
    assert len(text_content) <= 280, "Tweet content must not exceed 280 characters"

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

    # Initialize handler for database operations
    handler = TwitterHandler()

    # Publish the tweet
    ai_logger.action("Publishing tweet.", agent_id, account_id, agent_name)
    # Acquire semaphore to respect rate limits
    await semaphore.acquire()
    try:
        tweet = await twitter.create_tweet(text=text_content)
    finally:
        # Release the semaphore
        semaphore.release()

    if not tweet or "id" not in tweet:
        logger.error("Failed to publish tweet")
        ai_logger.result("Failed to publish tweet", agent_id, account_id, agent_name)
        return {"status": "error", "message": "Failed to publish tweet"}

    # Index the tweet
    username = twitter.get_username()
    await indexing.twitter_index_by_id(twitter_connection=twitter_connection, tweet_id=tweet["id"], data_store=data_store)

    # Postcondition - ensure we have the publishing results
    result = {
        "status": "success",
        "values": {
            "context": {
                "tweet": text_content,
            },
            "output": {
                "tweet": {
                    "text": text_content,
                    "url": f"https://x.com/{username}/status/{tweet['id']}",
                },
            },
        },
    }

    ai_logger.result(f"Successfully published tweet {tweet['id']}", agent_id, account_id, agent_name)
    logger.info(f"Successfully published tweet {tweet['id']}")
    return result

