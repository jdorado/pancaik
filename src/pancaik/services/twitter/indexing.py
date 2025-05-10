"""
Twitter indexing tools for agents.

This module provides tools for indexing tweets from users and mentions.
"""

from typing import Any, Dict, List, Optional

from ...core.config import get_config, logger
from ...core.connections import ConnectionHandler
from ...tools.base import tool
from . import client
from .handlers import TwitterHandler
from ...core.ai_logger import ai_logger


@tool()
async def twitter_index_mentions(twitter_connection: str, target_handle: str, data_store: dict) -> Optional[List[Dict]]:
    """
    Index mentions for a target Twitter handle.

    Args:
        twitter_connection: Connection ID for Twitter credentials
        target_handle: Twitter handle to search mentions for
        data_store: Dictionary containing agent context for AI logging

    Returns:
        List of processed mention tweets or None if not found
    """
    # Preconditions
    assert data_store is not None, "data_store must be provided for AI logging"
    agent_id = data_store.get("agent_id")
    owner_id = data_store.get("config", {}).get("owner_id")
    agent_name = data_store.get("config", {}).get("name")

    ai_logger.thinking(f"Preparing to index mentions for {target_handle}...", agent_id, owner_id, agent_name)
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

    ai_logger.action(f"Searching for mentions of @{username}...", agent_id, owner_id, agent_name)
    # Search for mentions
    mentions = await twitter.search(query)

    if not mentions:
        logger.info(f"No mentions found for @{username}")
        ai_logger.result(f"No mentions found for @{username}", agent_id, owner_id, agent_name)
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
        ai_logger.action(f"Indexed {len(new_mentions)} new mentions for @{username}", agent_id, owner_id, agent_name)
    else:
        logger.info(f"No new mentions to index for @{username}")
        ai_logger.action(f"No new mentions to index for @{username}", agent_id, owner_id, agent_name)

    # Postcondition - ensure we have the indexing results
    result = {
        "status": "success",
        "username": username,
        "total_mentions_found": len(mentions),
        "indexed_count": len(new_mentions),
        "already_indexed": len(existing_ids),
    }
    ai_logger.result(f"Indexing complete for @{username}: {len(new_mentions)} new, {len(existing_ids)} already indexed.", agent_id, owner_id, agent_name)
    return result


@tool()
async def index_tweet_by_id(twitter_connection: str, tweet_id: str, data_store: dict) -> Dict[str, Any]:
    """
    Indexes a single tweet by its ID.

    Args:
        twitter_connection: Connection ID for Twitter credentials
        tweet_id: The ID of the tweet to index
        data_store: Dictionary containing agent context for AI logging

    Returns:
        Dictionary with indexing operation results
    """
    # Preconditions
    assert tweet_id, "Tweet ID must be provided"
    assert data_store is not None, "data_store must be provided for AI logging"
    agent_id = data_store.get("agent_id")
    owner_id = data_store.get("config", {}).get("owner_id")
    agent_name = data_store.get("config", {}).get("name")

    ai_logger.thinking(f"Preparing to index tweet {tweet_id}...", agent_id, owner_id, agent_name)
    # Return immediately if tweet_id is 0 or not provided
    if not tweet_id or tweet_id == "0":
        logger.warning("Tweet ID not provided or is 0, skipping indexing")
        ai_logger.result(f"Tweet ID not provided or is 0, skipping indexing for {tweet_id}", agent_id, owner_id, agent_name)
        return {"status": "skipped", "tweet_id": tweet_id, "indexed_count": 0, "message": "Tweet ID not provided or is 0"}

    # Get database instance from config
    db = get_config("db")
    if db is None:
        raise ValueError("Database not initialized in config")

    # Initialize connection handler with db
    connection_handler = ConnectionHandler(db)
    twitter = await client.get_client(twitter_connection, connection_handler)

    # Get the semaphore for Twitter API rate limiting
    semaphore = get_config("twitter_semaphore")
    assert semaphore is not None, "Twitter semaphore must be available in config"

    # Ensure we have a handler for database operations
    handler = TwitterHandler()

    # Check if tweet is already indexed
    existing_ids = await handler.get_existing_tweet_ids([tweet_id])
    if tweet_id in existing_ids:
        logger.info(f"Tweet {tweet_id} is already indexed")
        return {"status": "already_indexed", "tweet_id": tweet_id, "indexed_count": 0}

    # Acquire semaphore to respect rate limits
    await semaphore.acquire()
    try:
        ai_logger.action(f"Fetching tweet {tweet_id} from Twitter API...", agent_id, owner_id, agent_name)
        # Fetch the tweet
        tweet = await twitter.get_tweet(tweet_id)

        if not tweet:
            logger.info(f"Tweet {tweet_id} not found or not accessible")
            return {"status": "tweet_not_found", "tweet_id": tweet_id, "indexed_count": 0}

        # Insert tweet into database
        await handler.insert_tweets([tweet])
        logger.info(f"Successfully indexed tweet {tweet_id}")
        ai_logger.result(f"Successfully indexed tweet {tweet_id}", agent_id, owner_id, agent_name)
        # Postcondition - ensure we have the indexing result
        result = {"status": "success", "tweet_id": tweet_id, "indexed_count": 1, "tweet_data": tweet}
        return result

    except Exception as e:
        logger.error(f"Error indexing tweet {tweet_id}: {str(e)}")
        ai_logger.result(f"Error indexing tweet {tweet_id}: {str(e)}", agent_id, owner_id, agent_name)
        return {"status": "error", "tweet_id": tweet_id, "error": str(e), "indexed_count": 0}
    finally:
        # Always release the semaphore
        semaphore.release()
