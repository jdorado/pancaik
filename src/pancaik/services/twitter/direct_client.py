"""
High-level Twitter client providing clean abstractions for Twitter operations.

This module combines the low-level access with business logic and error handling
to provide a comprehensive client for Twitter operations.
"""

import io
from typing import Dict, List, Optional, Union

import aiohttp

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
        - On error: None
    """
    try:
        # Handle retweet case when text is empty but quote_id is provided
        if not text and quote_id:
            resp = await api.send_tweet("", twitter, quote_tweet_id=quote_id)
            if resp:
                logger.info(f"TWEET: {twitter.get('username')} retweeted tweet {quote_id}")
                return {"retweet": quote_id}
            return None

        # Process media if present
        media_ids = await process_images(twitter, images) if images else None
        
        # Send tweet
        resp = await api.send_tweet(text, twitter, reply_to_id=reply_id, quote_tweet_id=quote_id)
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
                logger.info(f"Fetched {len(tweets)} tweets for query '{query}'")
                return [format_tweet(t) for t in tweets if t is not None and isinstance(t, dict)]
    except Exception as e:
        logger.warning(f"Search error for user '{username}': {e}")

    return None


async def get_tweet(tweet_id: str, twitter: Dict) -> Optional[Dict]:
    """Retrieve a single tweet by its ID."""
    username = twitter.get("username", "Unknown")
    try:
        tweet = await api.get_tweet(tweet_id, twitter)
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
