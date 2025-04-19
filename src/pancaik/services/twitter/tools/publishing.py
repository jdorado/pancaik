"""
Twitter publishing tools for agents.

This module provides tools for publishing tweets and tweet threads.
"""

from typing import Any, Dict, List, Optional

from ....tools.base import tool
from .. import client


@tool
async def publish_tweet(tweet: str, data_store: Dict[str, Any], reply_to_id: Optional[str] = None, quote_tweet_id: Optional[str] = None):
    """
    Publishes a tweet with the given content.

    Args:
        tweet: Content of the tweet to publish
        data_store: Agent's data store containing configuration and state
        reply_to_id: Optional ID of tweet to reply to
        quote_tweet_id: Optional ID of tweet to quote

    Returns:
        Confirmation of tweet publication
    """
    # Extract required configuration from data_store
    credentials = data_store.get("config", {}).get("twitter", {}).get("credentials", {})
    assert credentials, "Twitter credentials must be in the agent's data store"

    # Publish the tweet
    resp = await client.create_tweet(credentials, tweet, reply_id=reply_to_id, quote_id=quote_tweet_id)

    # Handle rate limit (TooManyRequests)
    if isinstance(resp, dict) and resp.get("should_exit"):
        return {"status": "rate_limited", "should_exit": True, "error": resp.get("error", "rate_limited"), "values": {"tweet_text": tweet}}

    # Handle 403 Forbidden (tweet id 0)
    if isinstance(resp, dict) and resp.get("tweet_id") == 0:
        return {
            "status": "forbidden",
            "tweet_id": 0,
            "error": resp.get("error", "forbidden"),
            "values": {"tweet_id": 0, "tweet_text": tweet},
        }

    # Success
    if resp and "id" in resp:
        tweet_id = resp["id"]
        url = f"https://x.com/{credentials.get('username', 'user')}/status/{tweet_id}"
        return {
            "status": "success",
            "tweet_id": tweet_id,
            "url": url,
            "text": tweet,
            "values": {"tweet_id": tweet_id, "tweet_url": url, "tweet_text": tweet},
        }
    else:
        return {"status": "error", "message": "Failed to publish tweet", "text": tweet}


@tool
async def create_tweet_thread(tweets: List[str], data_store: Dict[str, Any]):
    """
    Creates a thread of tweets.

    Args:
        tweets: List of tweet contents to publish as a thread
        data_store: Agent's data store containing configuration and state

    Returns:
        Confirmation of thread creation
    """
    # Preconditions
    assert tweets and len(tweets) > 0, "At least one tweet must be provided"

    # Extract required configuration from data_store
    credentials = data_store.get("config", {}).get("twitter", {}).get("credentials", {})
    assert credentials, "Twitter credentials must be in the agent's data store"

    # Create the thread
    first_id = await client.create_thread(credentials, tweets)

    if first_id:
        url = f"https://x.com/{credentials.get('username', 'user')}/status/{first_id}"
        return {
            "status": "success",
            "thread_id": first_id,
            "url": url,
            "tweet_count": len(tweets),
            "values": {"thread_id": first_id, "thread_url": url, "tweet_count": len(tweets)},
        }
    else:
        return {"status": "error", "message": "Failed to create thread", "tweet_count": len(tweets)}
