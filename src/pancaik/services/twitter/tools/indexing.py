"""
Twitter indexing tools for agents.

This module provides tools for indexing tweets from users and mentions.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict

from ....core.config import get_config, logger
from ....tools.base import tool
from .. import client
from ..handlers import TwitterHandler


@tool
async def index_user_tweets(twitter_handle: str, data_store: Dict[str, Any], twitter_user_id: str = None, max_tweets: int = 100):
    """
    Indexes tweets from a specific user for searching later.

    Args:
        twitter_handle: Twitter handle/username to index
        data_store: Agent's data store containing configuration and state
        twitter_user_id: Optional Twitter user ID if known
        max_tweets: Maximum number of tweets to fetch (default: 100)

    Returns:
        Dictionary with indexing operation results
    """
    # Preconditions
    assert twitter_handle, "Twitter handle must be provided"
    assert max_tweets > 0, "max_tweets must be positive"

    # Extract required configuration from data_store
    credentials = data_store.get("config", {}).get("twitter", {}).get("credentials", {})
    assert credentials, "Twitter credentials must be in the agent's data store"

    # Get the semaphore for Twitter API rate limiting
    semaphore = get_config("twitter_semaphore")
    assert semaphore is not None, "Twitter semaphore must be available in config"

    # Ensure we have a handler for database operations
    handler = TwitterHandler()

    # Get or create the user document
    user = await handler.get_user(twitter_handle) or {"_id": twitter_handle, "user_id": twitter_user_id, "tries": 0}

    # Acquire semaphore to respect rate limits
    await semaphore.acquire()
    try:
        # Get latest tweets
        handle = user["_id"]
        user_id = user.get("user_id")

        logger.info(f"Indexing tweets for user {handle}")

        # Fetch latest tweets
        latest_tweets = await client.get_latest_tweets(credentials, handle, user_id, max_tweets)

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
        logger.error(f"Error indexing tweets for user {twitter_handle}: {str(e)}")
        return {"status": "error", "username": twitter_handle, "error": str(e), "indexed_count": 0}
    finally:
        # Always release the semaphore
        semaphore.release()


@tool
async def index_tweets(data_store: Dict[str, Any]):
    """
    Indexes tweets from multiple users specified in data_store.

    Args:
        data_store: Agent's data store containing configuration, state, and user info

    Returns:
        Dictionary with indexing operation results
    """
    # Preconditions
    assert data_store, "Data store must be provided"

    # Get twitter configuration
    twitter = data_store.get("config", {}).get("twitter", {})

    # Extract required configuration from twitter object
    credentials = twitter.get("credentials", {})
    assert credentials, "Twitter credentials must be in the agent's data store"

    # Check for followed users in twitter config
    followed_users = twitter.get("followed_users", {})
    assert isinstance(followed_users, dict), "followed_users should be a dictionary where keys are Twitter handles"

    if not followed_users:
        logger.warning("No Twitter followed users found in data store")
        return {"status": "error", "message": "No Twitter followed users found in data store", "indexed_count": 0}

    # Get the Twitter handler for database operations
    handler = TwitterHandler()

    # Get latest indexed data by querying all users in a single database call
    latest_indexed = await handler.get_users(list(followed_users.keys()))

    # Setup users data with latest indexed info, merging database data with followed_users config
    processed_users = {}
    for user in latest_indexed:
        handle = user["_id"]
        if handle in processed_users:
            processed_users[handle].update(user)
        else:
            processed_users[handle] = user
            # Add any configuration from followed_users
            if handle in followed_users and isinstance(followed_users[handle], dict):
                for key, value in followed_users[handle].items():
                    if key not in processed_users[handle]:
                        processed_users[handle][key] = value

    # Ensure all followed users are in processed_users with their config values
    for handle, config in followed_users.items():
        if handle not in processed_users:
            processed_users[handle] = {"_id": handle}
            # Add configuration values if available
            if isinstance(config, dict):
                processed_users[handle].update(config)

    # Skip users if date is less than x_hourly_limit
    default_index_frequency = twitter.get("default_index_user_frequency", 60)  # Default to 60 minutes if not specified
    current_time = datetime.utcnow()
    filtered_users = {}
    for user, params in processed_users.items():
        last_indexed = params.get("date")
        x_minute_limit = params.get("index_minutes", default_index_frequency)
        if not last_indexed or (current_time - last_indexed).total_seconds() / 60 >= x_minute_limit:
            filtered_users[user] = params

    if not filtered_users:
        logger.info("No users need indexing at this time")
        return {"status": "no_action_needed", "message": "No users need indexing at this time", "indexed_count": 0}

    # Setup concurrent indexing
    tasks = []
    count = 0
    max_concurrent_indexing_users = get_config("twitter_max_concurrent_indexing_users", 30)

    # Create tasks for each user
    for handle, user_data in filtered_users.items():
        # Use existing index_user_tweets function
        task = index_user_tweets(
            twitter_handle=handle,
            data_store=data_store,
            twitter_user_id=user_data.get("user_id"),
            max_tweets=user_data.get("max_tweets", 100),
        )
        tasks.append(task)
        count += 1
        if count >= max_concurrent_indexing_users:
            break

    # Run tasks concurrently
    results = await asyncio.gather(*tasks)

    # Calculate total results
    total_indexed = sum(result.get("indexed_count", 0) for result in results)

    return {
        "status": "success",
        "indexed_count": total_indexed,
        "users_processed": count,
        "user_results": results,
        "values": {"indexed_count": total_indexed, "users_processed": count},
    }


@tool
async def index_mentions(data_store: Dict[str, Any]):
    """
    Indexes mentions of the agent's Twitter account.

    Args:
        data_store: Agent's data store containing configuration and state

    Returns:
        Dictionary with indexing operation results
    """
    # Preconditions
    assert data_store, "Data store must be provided"

    # Extract required configuration from data_store
    credentials = data_store.get("config", {}).get("twitter", {}).get("credentials", {})
    assert credentials, "Twitter credentials must be in the agent's data store"

    # Get the username for constructing the search query
    username = credentials.get("username")
    assert username, "Twitter username must be in the credentials"

    # Create query to search for mentions excluding retweets
    query = f"(@{username}) -is:retweet"

    # Ensure we have a handler for database operations
    handler = TwitterHandler()

    # Search for mentions
    mentions = await client.search(query, credentials)

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


@tool
async def index_tweet_by_id(tweet_id: str, data_store: Dict[str, Any]):
    """
    Indexes a single tweet by its ID.

    Args:
        tweet_id: The ID of the tweet to index
        data_store: Agent's data store containing configuration and state

    Returns:
        Dictionary with indexing operation results
    """
    # Return immediately if tweet_id is 0
    if tweet_id == 0:
        return {"status": "skipped", "tweet_id": tweet_id, "indexed_count": 0, "message": "tweet_id is 0, skipping indexing"}
    # Preconditions
    assert tweet_id, "Tweet ID must be provided"
    assert data_store, "Data store must be provided"

    # Extract required configuration from data_store
    credentials = data_store.get("config", {}).get("twitter", {}).get("credentials", {})
    assert credentials, "Twitter credentials must be in the agent's data store"

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
        tweet = await client.get_tweet(tweet_id, credentials)

        if not tweet:
            logger.info(f"Tweet {tweet_id} not found or not accessible")
            return {"status": "tweet_not_found", "tweet_id": tweet_id, "indexed_count": 0}

        # Insert tweet into database
        await handler.insert_tweets([tweet])
        logger.info(f"Successfully indexed tweet {tweet_id}")

        # Postcondition - ensure we have the indexing result
        result = {"status": "success", "tweet_id": tweet_id, "indexed_count": 1, "tweet_data": tweet}

        return result

    except Exception as e:
        logger.error(f"Error indexing tweet {tweet_id}: {str(e)}")
        return {"status": "error", "tweet_id": tweet_id, "error": str(e), "indexed_count": 0}
    finally:
        # Always release the semaphore
        semaphore.release()
