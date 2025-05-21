"""
High-level Twitter client providing clean abstractions for Twitter operations.

This module provides functions for both direct API calls via Tweepy and our custom X-API service,
handling authentication and providing a clean interface to Twitter operations.

X-API Service Repository: https://github.com/jdorado/x-api-service
"""

import io
from typing import Any, Dict, List, Optional, Union

import aiohttp
import tweepy
from tweepy.asynchronous import AsyncClient

from ...core.config import get_config, logger
from .models import format_tweet


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


# Direct API endpoints

async def login(credentials: Dict[str, str]) -> Dict[str, Any]:
    """Validate Twitter credentials by trying to get the user's profile.
    
    Args:
        credentials: Twitter API credentials
        
    Returns:
        Dictionary containing the user's profile if credentials are valid
        
    Raises:
        Exception: If credentials are invalid or request fails
    """
    assert credentials, "Credentials must not be empty"
    x_api = get_x_api_url()
    url = f"{x_api}/login"
    result = await post(url, credentials)
    if not result or "error" in result:
        logger.warning(f"Login failed: {result.get('error') if result else 'Unknown error'}")
        raise ValueError("Invalid Twitter credentials")
    return result


async def get_profile(user: str, credentials: Dict[str, str]) -> Dict[str, Any]:
    """Get a Twitter user's profile information."""
    assert user, "User must not be empty"
    assert credentials, "Credentials must not be empty"
    x_api = get_x_api_url()
    url = f"{x_api}/profile/{user}"
    return await post(url, credentials)


async def get_tweets_raw(user_id: str, credentials: Dict[str, str]) -> Dict[str, Any]:
    """Get raw tweets from a specific user."""
    assert user_id, "User ID must not be empty"
    assert credentials, "Credentials must not be empty"
    x_api = get_x_api_url()
    url = f"{x_api}/tweets/{user_id}"
    return await post(url, credentials)


async def send_tweet_raw(
    text: str, credentials: Dict[str, str], reply_to_id: Optional[str] = None, quote_tweet_id: Optional[str] = None
) -> Dict[str, Any]:
    """Send a tweet (raw API call)."""
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


async def search_raw(query: str, credentials: Dict[str, str]) -> Optional[list]:
    """Search for tweets (raw API call)."""
    assert query, "Search query must not be empty"
    assert credentials, "Credentials must not be empty"
    x_api = get_x_api_url()
    url = f"{x_api}/search"
    body = {**credentials, "query": query}
    result = await post(url, body)
    return result["tweets"] if result and "tweets" in result else None


async def get_tweet_raw(tweet_id: str, credentials: Dict[str, str]) -> Dict[str, Any]:
    """Get a specific tweet by ID (raw API call)."""
    assert tweet_id, "Tweet ID must not be empty"
    assert credentials, "Credentials must not be empty"
    x_api = get_x_api_url()
    url = f"{x_api}/tweet/{tweet_id}"
    body = {**credentials}
    return await post(url, body)


async def get_following_raw(user_id: str, credentials: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Get following list for a specific user (raw API call)."""
    assert user_id, "User ID must not be empty"
    assert credentials, "Credentials must not be empty"
    x_api = get_x_api_url()
    url = f"{x_api}/following/{user_id}"
    result = await post(url, credentials)
    return result


# High-level operations

async def download_image(url: str) -> Optional[bytes]:
    """Download image from URL."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
        logger.warning(f"Image download failed: {url}")
    except Exception as e:
        logger.warning(f"Download error for URL '{url}': {e}")
    return None


async def upload_media(twitter: Dict[str, str], data: bytes, filename: str = "image.jpg") -> Optional[int]:
    """Upload media to Twitter."""
    try:
        tweepy_api = get_api(twitter)
        media = tweepy_api.media_upload(filename, file=io.BytesIO(data))
        return media.media_id
    except Exception as e:
        logger.warning(f"Media upload failed for user '{twitter.get('username', 'Unknown')}': {e}")
    return None


async def process_images(twitter: Dict, urls: Union[str, List[str]]) -> List[int]:
    """Process and upload multiple images."""
    urls = [urls] if isinstance(urls, str) else urls
    media_ids = []
    for url in urls:
        data = await download_image(url)
        if data:
            media_id = await upload_media(twitter, data)
            if media_id:
                media_ids.append(media_id)
    return media_ids


async def create_tweet(
    twitter: Dict,
    text: str,
    images: Union[str, List[str]] = None,
    reply_id: Optional[int] = None,
    quote_id: Optional[int] = None,
) -> Optional[Dict]:
    """Create a tweet with optional media, reply, or quote."""
    try:
        # Handle retweet case when text is empty but quote_id is provided
        if not text and quote_id:
            resp = await send_tweet_raw("", twitter, quote_tweet_id=quote_id)
            if resp:
                logger.info(f"TWEET: {twitter.get('username')} retweeted tweet {quote_id}")
                return {"retweet": quote_id}
            return None

        # Process media if present
        media_ids = await process_images(twitter, images) if images else None

        # Send tweet
        resp = await send_tweet_raw(text, twitter, reply_to_id=reply_id, quote_tweet_id=quote_id)
        if resp and "id" in resp:
            url = f"https://x.com/A/status/{resp['id']}"
            logger.info(f"TWEET: {twitter.get('username')} published {url}")
            return resp
        elif resp and "retweet" in resp:
            logger.info(f"TWEET: {twitter.get('username')} published retweet {resp['retweet']}")
            return resp

    except Exception as e:
        if "duplicate" in str(e):
            raise e
        else:
            logger.error(f"Tweet creation error for user '{twitter.get('username', 'Unknown')}': {e}")
            raise e
    return None


async def create_thread(twitter: Dict, texts: List[str], image_urls: Union[str, List[str]] = None) -> Optional[int]:
    """Create a thread of tweets."""
    if not texts:
        logger.warning(f"No texts provided for thread by user '{twitter.get('username', 'Unknown')}'.")
        return None

    first_id = None
    prev_id = None
    for text in texts:
        resp = await create_tweet(twitter, text, image_urls if not prev_id else None, reply_id=prev_id)
        if resp:
            first_id = first_id or resp["id"]
            prev_id = resp["id"]
        else:
            logger.warning(f"Failed to post tweet in thread for user '{twitter.get('username', 'Unknown')}': {text}")
            break
    return first_id


async def get_latest_tweets(twitter: Dict, username: str, user_id: Optional[str] = None) -> Optional[List[Dict]]:
    """Fetch the latest tweets for a user."""
    try:
        # If user_id not provided, try to get it from profile
        if not user_id:
            try:
                profile = await get_profile(username, twitter)
                if profile and "id" in profile:
                    user_id = profile["id"]
                    logger.info(f"Retrieved user ID '{user_id}' for username '{username}'")
                else:
                    logger.warning(f"Could not get user ID from profile for user '{username}'")
                    return None
            except Exception as e:
                logger.warning(f"Failed to get profile for user '{username}': {e}")
                return None

        tweets = await get_tweets_raw(user_id, twitter)

        # Check if tweets is valid
        if not tweets:
            logger.warning(f"No tweets returned for user '{username}'")
            return None

        # Handle case where tweets is a dictionary with a 'tweets' key
        if isinstance(tweets, dict):
            if "tweets" in tweets and isinstance(tweets["tweets"], list):
                tweets = tweets["tweets"]
                logger.info(f"Extracted tweets list from dictionary response for user '{username}'")
            else:
                # Try to find any list in the dictionary that might contain tweets
                for key, value in tweets.items():
                    if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict) and "id" in value[0]:
                        tweets = value
                        logger.info(f"Found tweets list under key '{key}' for user '{username}'")
                        break
                else:
                    logger.warning(f"Could not find tweets list in dictionary response for user '{username}'")
                    return None

        # Handle case where tweets is a string or other non-list type
        if not isinstance(tweets, list):
            logger.warning(f"Invalid tweets data type for user '{username}': {type(tweets)}")
            return None

        if len(tweets) > 0:
            formatted_tweets = [format_tweet(t, user_id, username) for t in tweets if t is not None and isinstance(t, dict)]
            logger.info(f"Fetched {len(formatted_tweets)} tweets for user '{username}'")
            return formatted_tweets
        else:
            logger.warning(f"No tweets found for user '{username}'")
    except Exception as e:
        logger.warning(f"Failed to fetch tweets for user '{username}': {e}")
    return None


async def search(query: str, twitter: Dict) -> Optional[List[Dict]]:
    """Search tweets based on a query."""
    username = twitter.get("username", "Unknown")
    try:
        tweets = await search_raw(query, twitter)

        # Check if tweets is valid
        if tweets is not None:
            # Handle case where tweets is a dictionary with a 'tweets' key
            if isinstance(tweets, dict):
                if "tweets" in tweets and isinstance(tweets["tweets"], list):
                    tweets = tweets["tweets"]
                    logger.info(f"Extracted tweets list from dictionary response for search by user '{username}'")
                else:
                    # Try to find any list in the dictionary that might contain tweets
                    for key, value in tweets.items():
                        if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict) and "id" in value[0]:
                            tweets = value
                            logger.info(f"Found tweets list under key '{key}' for search by user '{username}'")
                            break
                    else:
                        logger.warning(f"Could not find tweets list in dictionary response for search by user '{username}'")
                        tweets = None

            if not isinstance(tweets, list):
                logger.warning(f"Invalid tweets data type from search for user '{username}': {type(tweets)}")
                tweets = None
            elif len(tweets) > 0:
                logger.info(f"Fetched {len(tweets)} tweets for query '{query}'")
                return [format_tweet(t) for t in tweets if t is not None and isinstance(t, dict)]
    except Exception as e:
        logger.warning(f"Search error for user '{username}': {e}")

    return None


async def get_tweet(tweet_id: str, twitter: Dict) -> Optional[Dict]:
    """Retrieve a single tweet by its ID."""
    username = twitter.get("username", "Unknown")
    try:
        tweet = await get_tweet_raw(tweet_id, twitter)
        if tweet:
            # Check if tweet is a dictionary
            if not isinstance(tweet, dict):
                logger.warning(f"Invalid tweet data type for ID '{tweet_id}' for user '{username}': {type(tweet)}")
            # Handle case where tweet might be nested in a response
            elif "tweet" in tweet and isinstance(tweet["tweet"], dict):
                logger.info(f"Fetched tweet '{tweet_id}' for user '{username}' (nested format)")
                return format_tweet(tweet["tweet"])
            elif "error" not in tweet:
                logger.info(f"Fetched tweet '{tweet_id}' for user '{username}'")
                return format_tweet(tweet)
    except Exception as e:
        logger.warning(f"Failed to fetch tweet '{tweet_id}' for user '{username}': {e}")

    return None


async def get_following(user_id: str, twitter: Dict) -> Optional[List[Dict]]:
    """Get following list for a specific user."""
    username = twitter.get("username", "Unknown")
    try:
        following = await get_following_raw(user_id, twitter)
        if following is not None:
            if isinstance(following, list):
                logger.info(f"Fetched {len(following)} following accounts for user ID '{user_id}'")
                return following
            logger.warning(f"Invalid following data type for user ID '{user_id}': {type(following)}")
    except Exception as e:
        logger.warning(f"Failed to fetch following for user ID '{user_id}' by user '{username}': {e}")
    return None
