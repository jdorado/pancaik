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

@tool()
async def index_tweet_by_id(twitter_connection: str, tweet_id: str) -> Dict[str, Any]:
    """
    Indexes a single tweet by its ID.

    Args:
        twitter_connection: Connection ID for Twitter credentials
        tweet_id: The ID of the tweet to index

    Returns:
        Dictionary with indexing operation results
    """
    # Preconditions
    assert tweet_id, "Tweet ID must be provided"
    
    # Return immediately if tweet_id is 0 or not provided
    if not tweet_id or tweet_id == "0":
        logger.warning("Tweet ID not provided or is 0, skipping indexing")
        return {
            "status": "skipped", 
            "tweet_id": tweet_id, 
            "indexed_count": 0, 
            "message": "Tweet ID not provided or is 0"
        }

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
        # Fetch the tweet
        tweet = await twitter.get_tweet(tweet_id)

        if not tweet:
            logger.info(f"Tweet {tweet_id} not found or not accessible")
            return {"status": "tweet_not_found", "tweet_id": tweet_id, "indexed_count": 0}

        # Insert tweet into database
        await handler.insert_tweets([tweet])
        logger.info(f"Successfully indexed tweet {tweet_id}")

        # Postcondition - ensure we have the indexing result
        result = {
            "status": "success", 
            "tweet_id": tweet_id, 
            "indexed_count": 1, 
            "tweet_data": tweet
        }

        return result

    except Exception as e:
        logger.error(f"Error indexing tweet {tweet_id}: {str(e)}")
        return {
            "status": "error", 
            "tweet_id": tweet_id, 
            "error": str(e), 
            "indexed_count": 0
        }
    finally:
        # Always release the semaphore
        semaphore.release()