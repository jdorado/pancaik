"""
Twitter indexing tools for agents.

This module provides tools for indexing tweets from users and mentions.
"""

from typing import List, Dict, Optional, Any

from ...core.config import logger, get_config
from ...core.connections import ConnectionHandler
from .handlers import TwitterHandler
from ...tools.base import tool
from . import client

@tool()
async def twitter_index_mentions(twitter_connection: str, target_handle: str) -> Optional[List[Dict]]:
    """
    Index mentions for a target Twitter handle.
    
    Args:
        twitter_connection: Connection ID for Twitter credentials
        target_handle: Twitter handle to search mentions for
        
    Returns:
        List of processed mention tweets or None if not found
    """
    # Get database instance from config
    db = get_config("db")
    if db is None:
        raise ValueError("Database not initialized in config")
        
    # Initialize connection handler with db
    connection_handler = ConnectionHandler(db)
    twitter = await client.get_client(twitter_connection, connection_handler)

    # Create query to search for mentions excluding retweets
    username = target_handle.replace("@", "").strip()
    query = f"(@{username}) -is:retweet"

    # Ensure we have a handler for database operations
    handler = TwitterHandler()

    # Search for mentions
    mentions = await twitter.search(query)

    if not mentions:
        logger.info(f"No mentions found for @{username}")
        return {"status": "no_mentions_found", "username": username, "indexed_count": 0}

    # Get existing tweet IDs to filter out already indexed mentions
    tweet_ids = [tweet["_id"] for tweet in mentions]
    existing_ids = await handler.get_existing_tweet_ids(tweet_ids)

    # Filter out existing mentions
    new_mentions = [tweet for tweet in mentions if tweet["_id"] not in existing_ids]

    # Insert new mentions into database
    if new_mentions:
        await handler.insert_tweets(new_mentions)
        logger.info(f"Indexed {len(new_mentions)} new mentions for @{username}")
    else:
        logger.info(f"No new mentions to index for @{username}")

    # Postcondition - ensure we have the indexing results
    result = {
        "status": "success",
        "username": username,
        "total_mentions_found": len(mentions),
        "indexed_count": len(new_mentions),
        "already_indexed": len(existing_ids),
    }

    return result