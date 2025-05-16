"""
Twitter indexing tools for agents.

This module provides tools for indexing tweets from users and mentions.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ...core.ai_logger import ai_logger
from ...core.config import get_config, logger
from ...core.connections import ConnectionHandler
from ...tools.base import tool
from . import client
from .client import TwitterClient
from .handlers import TwitterHandler

# Minimum time between indexing operations for a user
MIN_INDEX_INTERVAL = timedelta(hours=1)


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
    Rate limited to once per hour per user.

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

    # Initialize handlers
    connection_handler = ConnectionHandler(db)
    twitter = await client.get_client(twitter_connection, connection_handler)
    handler = TwitterHandler()

    # Check cooldown status
    in_cooldown, cooldown_info = await is_user_in_cooldown(handler, target_handle)
    if in_cooldown:
        logger.info(f"Rate limit: Too soon to index {target_handle}. Try again in {cooldown_info['wait_seconds']} seconds")
        return cooldown_info

    # Get the semaphore for Twitter API rate limiting
    semaphore = get_config("twitter_semaphore")
    assert semaphore is not None, "Twitter semaphore must be available in config"

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
        current_time = datetime.utcnow()
        user["date"] = current_time

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
            "last_indexed": current_time.isoformat(),
            "next_allowed": (current_time + MIN_INDEX_INTERVAL).isoformat()
        }
        return result
    except Exception as e:
        logger.error(f"Error indexing tweets for user {target_handle}: {str(e)}")
        return {"status": "error", "username": target_handle, "error": str(e), "indexed_count": 0}
    finally:
        # Always release the semaphore
        semaphore.release()


async def get_users_in_cooldown(
    handler: TwitterHandler,
    usernames: List[str]
) -> Dict[str, Dict[str, Any]]:
    """
    Check which users from a list are in cooldown period.
    
    Args:
        handler: TwitterHandler instance
        usernames: List of Twitter usernames to check
        
    Returns:
        Dictionary mapping usernames to their cooldown info if in cooldown, empty dict if not
    """
    # Get all users in a single query
    users = await handler.get_users(usernames)
    if not users:
        return {}
        
    current_time = datetime.utcnow()
    cooldown_info = {}
    
    for user in users:
        last_indexed = user.get("date")
        if not last_indexed:
            continue
            
        if (current_time - last_indexed) < MIN_INDEX_INTERVAL:
            time_until_next = last_indexed + MIN_INDEX_INTERVAL - current_time
            cooldown_info[user["_id"]] = {
                "status": "rate_limited",
                "username": user["_id"],
                "indexed_count": 0,
                "last_indexed": last_indexed.isoformat(),
                "next_allowed": (last_indexed + MIN_INDEX_INTERVAL).isoformat(),
                "wait_seconds": int(time_until_next.total_seconds())
            }
    
    return cooldown_info

async def is_user_in_cooldown(handler: TwitterHandler, username: str) -> tuple[bool, Optional[Dict[str, Any]]]:
    """
    Check if a user is in the cooldown period.
    
    Args:
        handler: TwitterHandler instance
        username: Twitter username to check
        
    Returns:
        Tuple of (is_in_cooldown, cooldown_info)
        cooldown_info contains timing details if in cooldown, None otherwise
    """
    cooldown_info = await get_users_in_cooldown(handler, [username])
    if username in cooldown_info:
        return True, cooldown_info[username]
    return False, None

@tool()
async def twitter_index_multiple(twitter_connection: str, target_handles: str, data_store: dict) -> Dict[str, Any]:
    """
    Index tweets from multiple Twitter users sequentially.
    Limited to 20 users per call and respects per-user cooldown periods.

    Args:
        twitter_connection: Connection ID for Twitter credentials
        target_handles: The handle(s) to index tweets from. Can be a single handle or multiple handles separated by newlines.
                      Handles can optionally include @ symbol which will be removed.
        data_store: Dictionary containing agent context for AI logging

    Returns:
        Dictionary with results for each handle
    """
    # Preconditions
    assert data_store is not None, "data_store must be provided for AI logging"
    assert isinstance(target_handles, str), "target_handles must be a string"
    
    # Split handles by newlines, remove @ symbols, and filter out empty strings
    handles = [h.strip().lstrip('@') for h in target_handles.split('\n') if h.strip()]
    
    agent_id = data_store.get("agent_id")
    account_id = data_store.get("config", {}).get("account_id")
    agent_name = data_store.get("config", {}).get("name")

    ai_logger.thinking(f"Preparing to index tweets for {len(handles)} users...", agent_id, account_id, agent_name)
    logger.info(f"Preparing to index tweets for {len(handles)} users...")

    # Initialize handler to check cooldown periods
    db = get_config("db")
    if db is None:
        raise ValueError("Database not initialized in config")
    handler = TwitterHandler()
    
    # Check cooldown status for all handles in a single query
    cooldown_info = await get_users_in_cooldown(handler, handles)
    
    # Separate handles into those we can process and those in cooldown
    handles_to_process = []
    skipped_handles = []
    
    for handle in handles:
        if handle in cooldown_info:
            skipped_handles.append(cooldown_info[handle])
        else:
            handles_to_process.append(handle)
            # Break if we have 20 valid handles
            if len(handles_to_process) >= 20:
                break
    
    if handles_to_process:
        ai_logger.action(
            f"Processing {len(handles_to_process)} users (skipped {len(skipped_handles)} in cooldown)...", 
            agent_id, account_id, agent_name
        )
    else:
        ai_logger.action(
            f"All {len(handles)} users are in cooldown period", 
            agent_id, account_id, agent_name
        )

    # Process handles not in cooldown sequentially
    processed_results = {}
    for handle in handles_to_process:
        try:
            ai_logger.action(f"Processing tweets for user: {handle}", agent_id, account_id, agent_name)
            result = await twitter_index_user(twitter_connection, handle, data_store)
            processed_results[handle] = result
        except Exception as e:
            logger.error(f"Error indexing tweets for {handle}: {str(e)}")
            processed_results[handle] = {
                "status": "error",
                "error": str(e),
                "indexed_count": 0
            }
    
    # Add skipped handles to results
    for info in skipped_handles:
        processed_results[info["username"]] = info

    remaining_handles = len(handles) - len(handles_to_process) - len(skipped_handles)
    ai_logger.result(
        f"Completed indexing tweets for {len(handles_to_process)} users "
        f"(skipped {len(skipped_handles)} in cooldown, {remaining_handles} not processed due to limit)",
        agent_id,
        account_id,
        agent_name
    )

    return {
        "status": "success",
        "results": processed_results,
        "total_handles_processed": len(handles_to_process),
        "total_handles_skipped": len(skipped_handles),
        "total_handles_requested": len(handles),
        "total_handles_remaining": remaining_handles,
        "handles_limited": len(handles) > (len(handles_to_process) + len(skipped_handles))
    }


@tool()
async def twitter_index_following(twitter_connection: str, target_handle: str, data_store: dict, min_followers: str = "100") -> Dict[str, Any]:
    """
    Indexes tweets from all users that a target user follows.

    Args:
        twitter_connection: Connection ID for Twitter credentials
        target_handle: Twitter handle whose following list we want to index
        data_store: Dictionary containing agent context for AI logging
        min_followers: Minimum number of followers required to index a user (default: "100")

    Returns:
        Dictionary with indexing operation results
    """
    # Cast min_followers to int as it may come as string
    min_followers_int = int(min_followers) if min_followers else 0
    
    # Get filtered following handles
    usernames, metadata = await get_filtered_following_handles(
        twitter_connection=twitter_connection,
        target_handle=target_handle,
        data_store=data_store,
        min_followers=min_followers_int
    )
    
    if metadata["status"] != "success":
        return metadata

    # Index tweets from filtered following users
    agent_id = data_store.get("agent_id")
    account_id = data_store.get("config", {}).get("account_id")
    agent_name = data_store.get("config", {}).get("name")
    
    ai_logger.action(
        f"Indexing tweets from {len(usernames)} following users (filtered from {metadata['total_count']} total)...", 
        agent_id, account_id, agent_name
    )
    
    # Convert usernames list to newline-separated string for twitter_index_multiple
    usernames_str = "\n".join(usernames)
    result = await twitter_index_multiple(twitter_connection, usernames_str, data_store)

    # Add following-specific metadata to result
    result["following_count"] = metadata["total_count"]
    result["filtered_following_count"] = metadata["filtered_count"]
    result["min_followers_threshold"] = min_followers_int
    result["source_user"] = target_handle

    ai_logger.result(
        f"Completed indexing tweets from following list of {target_handle} ({len(usernames)} users after filtering)",
        agent_id,
        account_id,
        agent_name
    )

    return result


async def get_filtered_following_handles(
    twitter_connection: str,
    target_handle: str,
    data_store: dict,
    min_followers: int = 100
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Gets filtered list of handles that a user follows based on criteria.

    Args:
        twitter_connection: Connection ID for Twitter credentials
        target_handle: Twitter handle whose following list we want to get
        data_store: Dictionary containing agent context for AI logging
        min_followers: Minimum number of followers required to include a user

    Returns:
        Tuple containing:
        - List of filtered usernames
        - Dict with metadata about the filtering process
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
    twitter: TwitterClient = await client.get_client(twitter_connection, connection_handler)

    # Ensure we have a handler for database operations
    handler = TwitterHandler()

    # Get or create the user document to get user_id
    user = await handler.get_user(target_handle)
    if not user or not user.get("user_id"):
        # Try to get user profile first
        logger.info(f"User {target_handle} not found or missing user_id, attempting to fetch profile")
        profile = await twitter.get_profile(target_handle)
        
        if profile and profile.get("id"):
            user = {
                "_id": target_handle,
                "user_id": profile["id"],
                "date": datetime.utcnow(),
                "tries": 0
            }
            await handler.update_user(user)
            user_id = profile["user_id"]
        else:
            # Fallback to indexing tweets if profile fetch fails
            user_result = await twitter_index_user(twitter_connection, target_handle, data_store)
            if user_result.get("status") != "success" or not user_result.get("user_id"):
                return [], {
                    "status": "error",
                    "username": target_handle,
                    "error": "Could not obtain user_id",
                    "filtered_count": 0,
                    "total_count": 0
                }
            user_id = user_result["user_id"]
    else:
        user_id = user["user_id"]

    ai_logger.action(f"Fetching following list for user {target_handle}...", agent_id, account_id, agent_name)
    # Get the following list
    following_list = await twitter.get_following(user_id)

    if not following_list:
        logger.info(f"No following users found for {target_handle}")
        ai_logger.result(f"No following users found for {target_handle}", agent_id, account_id, agent_name)
        return [], {
            "status": "no_following_found",
            "username": target_handle,
            "filtered_count": 0,
            "total_count": 0
        }

    # Filter and save user entries from following list
    filtered_following = []
    user_entries = []  # Collect all user entries for bulk update
    for following_user in following_list:
        if not following_user.get("username"):
            continue
        
        followers_count = following_user.get("followersCount", 0)
        
        # Skip users with fewer followers than minimum
        if followers_count < int(min_followers):
            logger.info(f"Skipping user {following_user['username']} with {followers_count} followers (minimum: {min_followers})")
            continue
            
        filtered_following.append(following_user)
        
        user_entry = {
            "_id": following_user["username"],
            "user_id": following_user["id"],
            "date": datetime.utcnow(),
            "tries": 0,
            "followers_count": following_user.get("followersCount"),
            "following_count": following_user.get("followingCount"),
            "is_verified": following_user.get("isVerified", False),
            "profile_image_url": following_user.get("profileImageUrl"),
            "name": following_user.get("name"),
            "bio": following_user.get("bio")
        }
        user_entries.append(user_entry)
    
    # Bulk update all user entries at once if we have any
    if user_entries:
        await handler.bulk_update_users(user_entries)

    # Extract usernames from filtered following list
    usernames = [user["username"] for user in filtered_following]

    metadata = {
        "status": "success",
        "username": target_handle,
        "filtered_count": len(filtered_following),
        "total_count": len(following_list),
        "min_followers_threshold": min_followers
    }

    return usernames, metadata
