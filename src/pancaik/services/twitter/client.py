"""
High-level Twitter client providing clean abstractions for Twitter operations.

This module combines the low-level API access with business logic and error handling
to provide a comprehensive client for Twitter operations.
"""

import io
from typing import Dict, List, Optional, Union

import aiohttp
from tweepy import Client
from tweepy.errors import TweepyException

from ...core.config import logger
from . import api
from .models import format_tweet


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
        tweepy_api = api.get_api(twitter)
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


def has_valid_api_credentials(twitter: Dict) -> bool:
    """Check if Twitter API credentials are present and non-empty."""
    required_keys = ["access_token", "access_token_secret"]
    for key in required_keys:
        if key not in twitter or not twitter[key]:
            assert key in twitter, f"Missing required credential: {key}"
            return False
    return True


async def create_tweet(
    twitter: Dict,
    text: str,
    images: Union[str, List[str]] = None,
    reply_id: Optional[int] = None,
    quote_id: Optional[int] = None,
) -> Optional[Dict]:
    """Create a tweet with optional media, reply, or quote.

    Returns:
        - On success: dict with tweet info (including 'id')
        - On TooManyRequests: {'should_exit': True, 'error': 'TooManyRequests'}
        - On 403 Forbidden: {'tweet_id': 0, 'error': '403 Forbidden'}
        - On other errors: None or raises
    """
    try:
        # Try non-API method first if no images
        if not images:
            resp = await api.send_tweet(text, twitter, reply_to_id=reply_id, quote_tweet_id=quote_id)
            if resp and "id" in resp:
                url = f"https://x.com/A/status/{resp['id']}"
                logger.info(f"TWEET: {twitter.get('username')} published direct {url}")
                return resp
            elif resp and "retweet" in resp:
                logger.info(f"TWEET: {twitter.get('username')} published retweet {resp['retweet']}")
                return resp

        # Check if API credentials are available
        has_api = has_valid_api_credentials(twitter)
        if not has_api:
            return None

        # Proceed with API-based tweet creation
        client = api.get_async_client(twitter)

        # Handle retweet case when text is empty but quote_id is provided
        if not text and quote_id:
            resp = await client.retweet(tweet_id=quote_id)
            if resp.data:
                logger.info(f"TWEET: {twitter.get('username')} retweeted tweet {quote_id}")
                return {"retweet": quote_id}
            return None

        media_ids = await process_images(twitter, images) if images else None
        resp = await client.create_tweet(
            text=text,
            in_reply_to_tweet_id=reply_id,
            quote_tweet_id=quote_id,
            media_ids=media_ids,
        )
        if resp.errors:
            logger.info(f"Tweet creation error for user '{twitter.get('username', 'Unknown')}': {resp.errors}")
            return None

        url = f'https://x.com/A/status/{resp.data["id"]}'
        logger.info(f"TWEET: {twitter.get('username')} published {url}")
        return resp.data
    except TweepyException as e:
        if "duplicate" in str(e):
            raise e
        elif "TooManyRequests" in str(e):
            logger.warning(f"X API Limit: Failed to create tweet for user '{twitter.get('username', 'Unknown')}'")
            return {"should_exit": True, "error": "TooManyRequests"}
        elif "403 Forbidden" in str(e) and "Tweet that is deleted or not visible" in str(e):
            logger.warning(f"Cannot reply to deleted/invisible tweet for user '{twitter.get('username', 'Unknown')}': {str(e)}")
            return {"tweet_id": 0, "error": "403 Forbidden"}
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


async def fetch_tweets_no_api(twitter: Dict, username: str, user_id: Optional[str] = None) -> Optional[List[Dict]]:
    """Fetch tweets using non-API method."""
    try:
        # If user_id not provided, try to get it from profile
        if not user_id:
            try:
                profile = await api.get_profile(username, twitter)
                if profile and "id" in profile:
                    user_id = profile["id"]
                    logger.info(f"Retrieved user ID '{user_id}' for username '{username}'")
                else:
                    logger.warning(f"Could not get user ID from profile for user '{username}'")
                    return None
            except Exception as e:
                logger.warning(f"Failed to get profile for user '{username}': {e}")
                return None

        tweets = await api.get_tweets(user_id, twitter)

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
            logger.info(f"Fetched {len(formatted_tweets)} tweets for user '{username}' using non-API method.")
            return formatted_tweets
        else:
            logger.warning(f"No tweets found for user '{username}' using non-API method.")
    except Exception as e:
        logger.warning(f"Non-API fetch failed for user '{username}': {e}")
    return None


async def fetch_tweets_api(client: Client, username: str, user_id: str, max_results: int = 10) -> Optional[List[Dict]]:
    """Fetch tweets using API-based strategies sequentially."""
    # Strategy 1: Get user with most recent tweet
    try:
        resp = await client.get_user(
            username=username,
            expansions=["most_recent_tweet_id"],
            tweet_fields=["created_at", "text"],
        )
        if resp.errors:
            logger.warning(f"Fetch strategy 1 error for user '{username}': {resp.errors}")
        else:
            tweets = resp.includes.get("tweets", [])
            if tweets and len(tweets) > 0:
                formatted = [format_tweet(t, resp.data.id, username) for t in tweets if t is not None and isinstance(t, dict)]
                logger.info(f"Fetched {len(formatted)} tweets for user '{username}' using strategy_1.")
                return formatted
    except TweepyException as e:
        if "TooManyRequests" in str(e):
            logger.info(f"X API Limit: Failed to fetch tweets for user '{username}' using strategy_1")
        else:
            logger.warning(f"Fetch strategy 1 failed for user '{username}': {e}")

    # Strategy 2: Get user by ID with most recent tweet
    try:
        resp = await client.get_user(
            id=user_id,
            expansions=["most_recent_tweet_id"],
            tweet_fields=["created_at", "text"],
        )
        if resp.errors:
            logger.warning(f"Fetch strategy 2 error for user '{username}': {resp.errors}")
        else:
            tweets = resp.includes.get("tweets", [])
            if tweets and len(tweets) > 0:
                formatted = [format_tweet(t, user_id, username) for t in tweets if t is not None and isinstance(t, dict)]
                logger.info(f"Fetched {len(formatted)} tweets for user '{username}' using strategy_2.")
                return formatted
    except TweepyException as e:
        if "TooManyRequests" in str(e):
            logger.info(f"X API Limit: Failed to fetch tweets for user '{username}' using strategy_2")
        else:
            logger.warning(f"Fetch strategy 2 failed for user '{username}': {e}")

    # Strategy 3: Get user's tweets excluding replies and retweets
    try:
        resp = await client.get_users_tweets(
            id=user_id,
            max_results=max_results,
            tweet_fields=["created_at", "text"],
            exclude=["replies", "retweets"],
        )
        if resp.errors:
            logger.warning(f"Fetch strategy 3 error for user '{username}': {resp.errors}")
        else:
            tweets = resp.data
            if tweets and len(tweets) > 0:
                formatted = [format_tweet(t, user_id, username) for t in tweets if t is not None and isinstance(t, dict)]
                logger.info(f"Fetched {len(formatted)} tweets for user '{username}' using strategy_3.")
                return formatted
    except TweepyException as e:
        if "TooManyRequests" in str(e):
            logger.info(f"X API Limit: Failed to fetch tweets for user '{username}' using strategy_3")
        else:
            logger.warning(f"Fetch strategy 3 failed for user '{username}': {e}")

    # Try more strategies if needed...
    logger.warning(f"All fetch strategies failed for user '{username}'.")
    return None


async def get_latest_tweets(twitter: Dict, username: str, user_id: str, max_results: int = 10) -> Optional[List[Dict]]:
    """Fetch the latest tweets for a user, trying non-API first."""
    # Attempt non-API method first
    tweets = await fetch_tweets_no_api(twitter, username, user_id)
    if tweets:
        return tweets

    # Check if API credentials are present
    has_api = has_valid_api_credentials(twitter)
    if not has_api:
        return None

    # Attempt API-based fetch
    client = api.get_async_client(twitter)
    tweets = await fetch_tweets_api(client, username.lstrip("@"), user_id, max_results)
    if tweets:
        return tweets

    logger.warning(f"Failed to fetch tweets for user '{username}' using all available methods.")
    return None


async def search(query: str, twitter: Dict) -> Optional[List[Dict]]:
    """Search tweets based on a query, trying non-API first."""
    username = twitter.get("username", "Unknown")
    # Attempt non-API search first
    try:
        tweets = await api.search(query, twitter)

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
                logger.info(f"Fetched {len(tweets)} tweets for query '{query}' using non-API search.")
                return [format_tweet(t) for t in tweets if t is not None and isinstance(t, dict)]
    except Exception as e:
        logger.warning(f"Direct search error for user '{username}': {e}")

    # Check if API credentials are present
    has_api = has_valid_api_credentials(twitter)
    if not has_api:
        return None

    # Attempt API-based search
    try:
        client = api.get_async_client(twitter)
        resp = await client.search_recent_tweets(
            query=query,
            tweet_fields=[
                "referenced_tweets",
                "created_at",
                "conversation_id",
                "author_id",
                "entities",
            ],
        )
        if resp.errors:
            logger.warning(f"Search API error for user '{username}': {resp.errors}")
            return None
        tweets = resp.data
        if tweets:
            logger.info(f"Fetched {len(tweets)} tweets for query '{query}' using API search.")
            return [format_tweet(t) for t in tweets if t is not None and isinstance(t, dict)]
    except Exception as e:
        if "TooManyRequests" in str(e):
            logger.info(f"X API Limit: Failed to search tweets for query '{query}' for user '{username}'")
        else:
            logger.warning(f"API search error for user '{username}': {e}")

    return None


async def get_tweet(tweet_id: str, twitter: Dict) -> Optional[Dict]:
    """Retrieve a single tweet by its ID, trying non-API first."""
    username = twitter.get("username", "Unknown")
    # Attempt non-API get_tweet first
    try:
        tweet = await api.get_tweet(tweet_id, twitter)
        if tweet:
            # Check if tweet is a dictionary
            if not isinstance(tweet, dict):
                logger.warning(f"Invalid tweet data type for ID '{tweet_id}' for user '{username}': {type(tweet)}")
            # Handle case where tweet might be nested in a response
            elif "tweet" in tweet and isinstance(tweet["tweet"], dict):
                logger.info(f"Fetched tweet '{tweet_id}' using non-API method for user '{username}' (nested format).")
                return format_tweet(tweet["tweet"])
            elif "error" not in tweet:
                logger.info(f"Fetched tweet '{tweet_id}' using non-API method for user '{username}'.")
                return format_tweet(tweet)
    except Exception as e:
        logger.warning(f"Direct get_tweet error for user '{username}': {e}")

    # Check if API credentials are present
    has_api = has_valid_api_credentials(twitter)
    if not has_api:
        return None

    # Attempt API-based get_tweet
    try:
        client = api.get_async_client(twitter)
        resp = await client.get_tweet(
            tweet_id,
            tweet_fields=[
                "referenced_tweets",
                "created_at",
                "conversation_id",
                "author_id",
                "entities",
            ],
        )
        if resp.errors:
            logger.warning(f"Get tweet API error for user '{username}': {resp.errors}")
            return None
        if resp.data:
            if not isinstance(resp.data, dict):
                logger.warning(f"Invalid tweet data type from API for ID '{tweet_id}' for user '{username}': {type(resp.data)}")
                return None
            logger.info(f"Fetched tweet '{tweet_id}' using API method for user '{username}'.")
            return format_tweet(resp.data)
        else:
            logger.warning(f"No tweet data returned for ID '{tweet_id}' for user '{username}'")
    except Exception as e:
        if "TooManyRequests" in str(e):
            logger.info(f"X API Limit: Failed to fetch tweet '{tweet_id}': {username}")
        else:
            logger.warning(f"API get_tweet error for user '{username}': {e}")

    return None
