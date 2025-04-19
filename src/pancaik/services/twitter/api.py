"""Twitter API client for interacting with the X-API service and official Twitter API.

This module provides functions for both direct API calls via Tweepy and our custom X-API service,
handling authentication and providing a clean interface to Twitter operations.

X-API Service Repository: https://github.com/jdorado/x-api-service
"""

from typing import Any, Dict, Optional

import aiohttp
import tweepy
from tweepy.asynchronous import AsyncClient

from ...core.config import get_config, logger


def get_x_api_url() -> str:
    """Get the X-API URL from config.

    Raises:
        ValueError: If x_api_url is not configured in the application.
    """
    x_api_url = get_config("x_api_url")
    if not x_api_url:
        logger.error("X-API URL not configured. Set x_api_url in the init() configuration.")
        raise ValueError("X-API URL not configured. Set x_api_url in the init() configuration.")
    return x_api_url


async def post(url: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Make a POST request to the X-API service."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as response:
                response.raise_for_status()
                return await response.json()
    except Exception as e:
        logger.warning(f"{url}: {str(e)}")
        return None


# Tweepy client initialization


def get_async_client(twitter: Dict[str, str]) -> AsyncClient:
    """Initialize Tweepy AsyncClient."""
    assert twitter, "Twitter credentials must not be empty"
    return AsyncClient(
        consumer_key=twitter["consumer_key"],
        consumer_secret=twitter["consumer_secret"],
        access_token=twitter.get("access_token"),
        access_token_secret=twitter.get("access_token_secret"),
        bearer_token=twitter["bearer_token"],
    )


def get_api(twitter: Dict[str, str]) -> tweepy.API:
    """Initialize Tweepy API client."""
    assert twitter, "Twitter credentials must not be empty"
    auth = tweepy.OAuth1UserHandler(
        consumer_key=twitter["consumer_key"],
        consumer_secret=twitter["consumer_secret"],
        access_token=twitter.get("access_token"),
        access_token_secret=twitter.get("access_token_secret"),
    )
    return tweepy.API(auth)


# X-API service endpoints


async def get_profile(user: str, credentials: Dict[str, str]) -> Dict[str, Any]:
    """Get a Twitter user's profile information."""
    assert user, "User must not be empty"
    assert credentials, "Credentials must not be empty"
    x_api = get_x_api_url()
    url = f"{x_api}/profile/{user}"
    return await post(url, credentials)


async def get_tweets(user_id: str, credentials: Dict[str, str]) -> Dict[str, Any]:
    """Get tweets from a specific user."""
    assert user_id, "User ID must not be empty"
    assert credentials, "Credentials must not be empty"
    x_api = get_x_api_url()
    url = f"{x_api}/tweets/{user_id}"
    return await post(url, credentials)


async def send_tweet(
    text: str, credentials: Dict[str, str], reply_to_id: Optional[str] = None, quote_tweet_id: Optional[str] = None
) -> Dict[str, Any]:
    """Send a tweet."""
    assert text or quote_tweet_id, "Tweet text must not be empty unless quoting a tweet"
    assert credentials, "Credentials must not be empty"
    x_api = get_x_api_url()
    url = f"{x_api}/tweet"
    body = {
        **credentials,
        "text": text,
        "reply_to_id": reply_to_id,
        "quote_tweet_id": quote_tweet_id,
    }
    result = await post(url, body)
    if result and "rest_id" in result:
        result["id"] = result["rest_id"]
        return result
    elif result and "retweet" in result:
        return result
    return None


async def search(query: str, credentials: Dict[str, str]) -> Optional[list]:
    """Search for tweets."""
    assert query, "Search query must not be empty"
    assert credentials, "Credentials must not be empty"
    x_api = get_x_api_url()
    url = f"{x_api}/search"
    body = {**credentials, "query": query}
    result = await post(url, body)
    return result["tweets"] if result and "tweets" in result else None


async def get_tweet(tweet_id: str, credentials: Dict[str, str]) -> Dict[str, Any]:
    """Get a specific tweet by ID."""
    assert tweet_id, "Tweet ID must not be empty"
    assert credentials, "Credentials must not be empty"
    x_api = get_x_api_url()
    url = f"{x_api}/tweet/{tweet_id}"
    body = {
        **credentials,
    }
    result = await post(url, body)
    return result
