"""
Twitter indexing tools for agents.

This module provides tools for indexing tweets from users and mentions.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from ...core.ai_logger import ai_logger
from ...core.config import get_config, logger
from ...core.connections import ConnectionHandler
from ...tools.base import tool
from . import client
from .handlers import TwitterHandler


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
    account_id = data_store.get("config", {}).get("account_id")
    agent_name = data_store.get("config", {}).get("name")

    ai_logger.thinking(f"Preparing to index mentions for {target_handle}...", agent_id, account_id, agent_name)
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

    ai_logger.action(f"Searching for mentions of @{username}...", agent_id, account_id, agent_name)
    # Search for mentions
    mentions = await twitter.search(query)

    if not mentions:
        logger.info(f"No mentions found for @{username}")
        ai_logger.result(f"No mentions found for @{username}", agent_id, account_id, agent_name)
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
        ai_logger.action(f"Indexed {len(new_mentions)} new mentions for @{username}", agent_id, account_id, agent_name)
    else:
        logger.info(f"No new mentions to index for @{username}")
        ai_logger.action(f"No new mentions to index for @{username}", agent_id, account_id, agent_name)

    # Postcondition - ensure we have the indexing results
    result = {
        "status": "success",
        "username": username,
        "total_mentions_found": len(mentions),
        "indexed_count": len(new_mentions),
        "already_indexed": len(existing_ids),
    }
    ai_logger.result(
        f"Indexing complete for @{username}: {len(new_mentions)} new, {len(existing_ids)} already indexed.",
        agent_id,
        account_id,
        agent_name,
    )
    return result


@tool()
async def twitter_index_by_id(twitter_connection: str, tweet_id: str, data_store: dict) -> Dict[str, Any]:
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
    account_id = data_store.get("config", {}).get("account_id")
    agent_name = data_store.get("config", {}).get("name")

    ai_logger.thinking(f"Preparing to index tweet {tweet_id}...", agent_id, account_id, agent_name)
    # Return immediately if tweet_id is 0 or not provided
    if not tweet_id or tweet_id == "0":
        logger.warning("Tweet ID not provided or is 0, skipping indexing")
        ai_logger.result(f"Tweet ID not provided or is 0, skipping indexing for {tweet_id}", agent_id, account_id, agent_name)
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
        ai_logger.action(f"Fetching tweet {tweet_id} from Twitter API...", agent_id, account_id, agent_name)
        # Fetch the tweet
        tweet = await twitter.get_tweet(tweet_id)

        if not tweet:
            logger.info(f"Tweet {tweet_id} not found or not accessible")
            return {"status": "tweet_not_found", "tweet_id": tweet_id, "indexed_count": 0}

        # Insert tweet into database
        await handler.insert_tweets([tweet])
        logger.info(f"Successfully indexed tweet {tweet_id}")
        ai_logger.result(f"Successfully indexed tweet {tweet_id}", agent_id, account_id, agent_name)
        # Postcondition - ensure we have the indexing result
        result = {"status": "success", "tweet_id": tweet_id, "indexed_count": 1, "tweet_data": tweet}
        return result

    except Exception as e:
        logger.error(f"Error indexing tweet {tweet_id}: {str(e)}")
        ai_logger.result(f"Error indexing tweet {tweet_id}: {str(e)}", agent_id, account_id, agent_name)
        return {"status": "error", "tweet_id": tweet_id, "error": str(e), "indexed_count": 0}
    finally:
        # Always release the semaphore
        semaphore.release()


@tool()
async def twitter_index_user(
    twitter_connection: str,
    target_handle: str,
    data_store: dict,
    twitter_user_id: str = None,
):
    """
    Indexes tweets from a specific user for searching later.

    Args:
        twitter_connection: Connection ID for Twitter credentials
        target_handle: Twitter handle/username to index
        data_store: Agent's data store containing configuration and state (required)
        twitter_user_id: Optional Twitter user ID if known

    Returns:
        Dictionary with indexing operation results
    """
    # Preconditions
    assert target_handle, "Twitter handle must be provided"
    assert data_store is not None, "data_store must be provided for AI logging"
    agent_id = data_store.get("agent_id")
    account_id = data_store.get("config", {}).get("account_id")
    agent_name = data_store.get("config", {}).get("name")

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

    # Get or create the user document
    user = await handler.get_user(target_handle) or {"_id": target_handle, "user_id": twitter_user_id, "tries": 0}

    # Acquire semaphore to respect rate limits
    try:
        # Get latest tweets
        handle = user["_id"]
        user_id = user.get("user_id")

        logger.info(f"Indexing tweets for user {handle}")
        ai_logger.action(f"Fetching latest tweets for user {handle}...", agent_id, account_id, agent_name)

        # Fetch latest tweets
        await semaphore.acquire()
        latest_tweets = await twitter.get_latest_tweets(handle, user_id)

        # Update user document based on fetch results
        user["date"] = datetime.utcnow()

        if not latest_tweets:
            logger.info(f"No tweets found for user {handle}")
            if user.get("tries", 0) >= 3:
                user["tries"] = 0
            else:
                user["tries"] = user.get("tries", 0) + 1

            await handler.update_user(user)
            return {"status": "no_tweets_found", "username": handle, "indexed_count": 0}

        # Update user_id if it's missing
        if not user.get("user_id") and latest_tweets:
            user["user_id"] = latest_tweets[0]["user_id"]

        # Reset tries counter on successful fetch
        user["tries"] = 0

        # Update user record
        await handler.update_user(user)

        # Check which tweets are already in the database
        tweet_ids = [tweet["_id"] for tweet in latest_tweets]
        existing_ids = await handler.get_existing_tweet_ids(tweet_ids)

        # Filter out existing tweets
        new_tweets = [tweet for tweet in latest_tweets if tweet["_id"] not in existing_ids]

        # Insert new tweets into database
        if new_tweets:
            await handler.insert_tweets(new_tweets)
            logger.info(f"Indexed {len(new_tweets)} new tweets for user {handle}")
        else:
            logger.info(f"No new tweets to index for user {handle}")

        # Postcondition - ensure we have the indexing results
        result = {
            "status": "success",
            "username": handle,
            "total_tweets_found": len(latest_tweets),
            "indexed_count": len(new_tweets),
            "already_indexed": len(existing_ids),
            "user_id": user.get("user_id"),
        }
        return result
    except Exception as e:
        logger.error(f"Error indexing tweets for user {target_handle}: {str(e)}")
        return {"status": "error", "username": target_handle, "error": str(e), "indexed_count": 0}
    finally:
        # Always release the semaphore
        semaphore.release()
