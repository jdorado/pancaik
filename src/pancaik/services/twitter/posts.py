"""
Twitter post loading tools for agents.

This module provides tools for loading and analyzing tweets from users.
"""

from json import tool
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from ...core.config import logger
from ...core.connections import ConnectionHandler
from .handlers import TwitterHandler
from . import client as twitter_client
from ...tools.base import tool
from ...core.config import get_config

@tool()
async def twitter_load_past_posts(
    twitter_connection: str,
    days_past: int,
    content_guidelines: Optional[str],
    data_store: dict,
    include_replies: bool = False
):
    """
    Loads previous Twitter posts for a user based on parameters.

    Args:
        twitter_connection: The username or connection identifier for Twitter.
        days_past: Number of days in the past to look for posts.
        content_guidelines: Optional guidelines for analyzing posts.
        data_store: Agent's data store containing configuration and state.
        include_replies: Whether to include replies in the loaded posts (default: False).

    Returns:
        Dictionary with loaded posts in 'values' for context update.
    """
    assert twitter_connection, "'twitter_connection' must be provided"
    assert days_past is not None, "'days_past' must be provided"
    assert data_store is not None, "data_store must be provided"
    assert isinstance(include_replies, bool), "include_replies must be a boolean"

    min_date = datetime.utcnow() - timedelta(days=int(days_past))

    logger.info(f"Loading past posts for connection {twitter_connection} for the past {days_past} days (include_replies={include_replies})")

    # Get database instance from config
    db = get_config("db")
    if db is None:
        raise ValueError("Database not initialized in config")
    
    connection_handler = ConnectionHandler(db)
    twitter = await twitter_client.get_client(twitter_connection, connection_handler)
    username = twitter.get_username()

    handler = TwitterHandler()
    posts = await handler.get_tweets_by_user(username, limit=1000, include_replies=include_replies)

    # Filter posts by min_date
    filtered_posts = [post for post in posts if post.get('created_at') and post['created_at'] >= min_date]

    # Limit to last 100 posts
    filtered_posts = filtered_posts[-100:]

    # TODO: Analyze posts according to content_guidelines and further processing

    return {"values": {"posts": filtered_posts}}