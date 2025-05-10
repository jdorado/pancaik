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
