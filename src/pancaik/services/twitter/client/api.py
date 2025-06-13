"""
Official Twitter API client implementation using tweepy.

This module provides a TwitterClient implementation that uses the official Twitter API
through the tweepy library for authentication and operations.
"""

import io
from typing import Any, Dict, List, Optional, Union

import aiohttp
import tweepy
from tweepy.asynchronous import AsyncClient
from tweepy.errors import TweepyException

from ....core.config import logger
from ..models import format_tweet
from .base import TwitterClient


class ApiTwitterClient(TwitterClient):
    """Twitter client using the official Twitter API via tweepy."""

    def __init__(
        self,
        bearer_token: Optional[str] = None,
        consumer_key: Optional[str] = None,
        consumer_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        access_token_secret: Optional[str] = None,
        screen_name: Optional[str] = None,
    ):
        """Initialize the API Twitter client.

        Args:
            bearer_token: Twitter API Bearer Token (for read-only operations)
            consumer_key: Twitter API Consumer Key
            consumer_secret: Twitter API Consumer Secret
            access_token: Twitter API Access Token
            access_token_secret: Twitter API Access Token Secret
            screen_name: Twitter screen name/username
        """
        self.bearer_token = bearer_token
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.access_token = access_token
        self.access_token_secret = access_token_secret
        self.screen_name = screen_name
        self._username = screen_name
        
        # Initialize the async client
        self.client = AsyncClient(
            bearer_token=bearer_token,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
            wait_on_rate_limit=True
        )
        
        # API v1.1 for media uploads
        if consumer_key and consumer_secret and access_token and access_token_secret:
            auth = tweepy.OAuth1UserHandler(
                consumer_key,
                consumer_secret,
                access_token,
                access_token_secret
            )
            self.api_v1 = tweepy.API(auth)
        else:
            self.api_v1 = None

    def get_username(self) -> str:
        """Get the username of the authenticated client."""
        return self._username or "unknown"

    async def test_connection(self) -> Dict[str, Any]:
        """Test the connection by attempting to get the authenticated user's info."""
        try:
            # Get the authenticated user's information
            user = await self.client.get_me()
            if user and user.data:
                self._username = user.data.username
                return {
                    "success": True,
                    "message": "Connection successful",
                    "user": {
                        "id": user.data.id,
                        "username": user.data.username,
                        "name": user.data.name,
                    }
                }
            else:
                return {
                    "success": False,
                    "message": "Failed to get user information"
                }
        except Exception as e:
            logger.error(f"Twitter API connection test failed: {str(e)}")
            return {
                "success": False,
                "message": f"Connection failed: {str(e)}"
            }

    async def get_profile(self, username: str) -> Optional[Dict[str, Any]]:
        """Get a Twitter user's profile information.

        Args:
            username: The username to get profile for

        Returns:
            Optional[Dict[str, Any]]: Profile data if successful, None otherwise
        """
        try:
            user = await self.client.get_user(
                username=username,
                user_fields=["created_at", "description", "location", "public_metrics", "verified"]
            )
            
            if user and user.data:
                return {
                    "id": user.data.id,
                    "username": user.data.username,
                    "name": user.data.name,
                    "description": user.data.description,
                    "location": user.data.location,
                    "created_at": user.data.created_at.isoformat() if user.data.created_at else None,
                    "verified": user.data.verified,
                    "public_metrics": user.data.public_metrics,
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get profile for {username}: {str(e)}")
            return None

    async def _download_image(self, url: str) -> Optional[bytes]:
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

    async def _process_images(self, urls: Union[str, List[str]]) -> List[int]:
        """Process and upload multiple images from URLs."""
        if isinstance(urls, str):
            urls = [urls]
        media_ids = []
        for url in urls:
            data = await self._download_image(url)
            if data:
                media_id = await self.upload_media(data)
                if media_id:
                    media_ids.append(media_id)
        return media_ids

    async def upload_media(self, data: bytes, filename: str = "image.jpg") -> Optional[int]:
        """Upload media to Twitter.

        Args:
            data: The binary data of the media file
            filename: The name of the file (default: image.jpg)

        Returns:
            Optional[int]: The media ID if successful, None otherwise
        """
        if not self.api_v1:
            logger.error("Media upload requires API v1.1 credentials (consumer and access tokens).")
            return None
        try:
            # Create a file-like object from bytes
            media_file = io.BytesIO(data)
            media_file.name = filename
            
            # Upload media using tweepy's media upload
            # Note: This requires API v1.1 access
            media = self.api_v1.media_upload(filename=filename, file=media_file)
            return media.media_id
        except Exception as e:
            logger.error(f"Failed to upload media: {str(e)}")
            return None

    async def retweet(self, tweet_id: str) -> Optional[Dict]:
        """Retweet a tweet.

        Args:
            tweet_id: The ID of the tweet to retweet.

        Returns:
            Optional[Dict]: Retweet data if successful, None otherwise.
        """
        try:
            resp = await self.client.retweet(tweet_id=tweet_id)
            if resp.data and resp.data.get("retweeted"):
                logger.info(f"TWEET: {self.get_username()} retweeted tweet {tweet_id}")
                return {"retweet": tweet_id, "id": resp.data.get("id")}
            logger.error(f"Failed to retweet {tweet_id}: {resp.errors}")
            return None
        except TweepyException as e:
            logger.error(f"Failed to retweet {tweet_id} for user '{self.get_username()}': {e}")
            return None

    async def create_tweet(self, text: str, image_urls: Union[str, List[str]] = None, reply_id=None, quote_id=None, media_data=None) -> Optional[Dict]:
        """Create a tweet with optional media, reply, or quote.
        Args:
            text: The text content of the tweet
            image_urls: Optional image URLs to attach
            reply_id: Optional ID of tweet to reply to
            quote_id: Optional ID of tweet to quote
            media_data: Optional media data (bytes) to attach to the tweet
        Returns:
            Optional[Dict]: Tweet data if successful, None otherwise
        """
        try:
            if not text and quote_id:
                return await self.retweet(tweet_id=quote_id)

            media_ids = []
            if image_urls:
                media_ids.extend(await self._process_images(image_urls))

            if media_data:
                if isinstance(media_data, list):
                    for media in media_data:
                        if isinstance(media, bytes):
                            media_id = await self.upload_media(media)
                            if media_id:
                                media_ids.append(media_id)
                elif isinstance(media_data, bytes):
                    media_id = await self.upload_media(media_data)
                    if media_id:
                        media_ids.append(media_id)

            tweet_params = {"text": text}
            if reply_id:
                tweet_params["in_reply_to_tweet_id"] = reply_id
            if quote_id:
                tweet_params["quote_tweet_id"] = quote_id
            if media_ids:
                tweet_params["media_ids"] = media_ids

            response = await self.client.create_tweet(**tweet_params)

            if response.errors:
                logger.error(f"Tweet creation error for user '{self.get_username()}': {response.errors}")
                return None

            if response.data:
                url = f'https://x.com/{self.get_username()}/status/{response.data["id"]}'
                logger.info(f"TWEET: {self.get_username()} published {url}")
                return {
                    "id": response.data["id"],
                    "text": response.data["text"],
                }
            return None
        except TweepyException as e:
            if "duplicate" in str(e):
                logger.warning(f"Duplicate tweet error for user '{self.get_username()}'.")
                raise e  # Re-raise to be handled by caller
            elif "TooManyRequests" in str(e):
                logger.warning(f"X API Limit: Failed to create tweet for user '{self.get_username()}'.")
            elif "403 Forbidden" in str(e) and "Tweet that is deleted or not visible" in str(e):
                logger.warning(f"Cannot reply to deleted/invisible tweet for user '{self.get_username()}': {e}")
            else:
                logger.error(f"Failed to create tweet for user '{self.get_username()}': {e}")
            return None

    async def create_thread(self, texts: List[str], image_urls: Union[str, List[str]] = None) -> Optional[str]:
        """Create a thread of tweets.

        Args:
            texts: List of text content for each tweet in the thread
            image_urls: Optional image URLs to attach to first tweet

        Returns:
            Optional[str]: ID of first tweet if successful, None otherwise
        """
        try:
            if not texts:
                return None
            
            first_tweet_id = None
            previous_tweet_id = None
            
            for i, text in enumerate(texts):
                # Only attach images to the first tweet
                current_image_urls = image_urls if i == 0 else None
                
                tweet = await self.create_tweet(
                    text=text,
                    image_urls=current_image_urls,
                    reply_id=previous_tweet_id
                )
                
                if not tweet:
                    logger.error(f"Failed to create tweet {i+1} in thread for user '{self.get_username()}'")
                    return first_tweet_id
                
                tweet_id = tweet["id"]
                if i == 0:
                    first_tweet_id = tweet_id
                previous_tweet_id = tweet_id
            
            return first_tweet_id
        except Exception as e:
            logger.error(f"Failed to create thread for user '{self.get_username()}': {e}")
            return None

    async def get_latest_tweets(self, username: str, user_id: Optional[str] = None, max_results: int = 10) -> Optional[List[Dict]]:
        """Fetch the latest tweets for a user using multiple API strategies.
        Args:
            username: The username to fetch tweets for
            user_id: Optional user ID if already known
            max_results: The maximum number of tweets to return
        Returns:
            Optional[List[Dict]]: List of tweet data if successful, None otherwise
        """
        if not user_id:
            try:
                profile = await self.get_profile(username)
                if profile and profile.get("id"):
                    user_id = profile["id"]
                else:
                    logger.warning(f"Could not get user ID from profile for user '{username}'")
                    return None
            except Exception as e:
                logger.warning(f"Failed to get profile for user '{username}': {e}")
                return None

        # Strategy 1: Get user with most recent tweet
        try:
            resp = await self.client.get_user(
                username=username,
                expansions=["most_recent_tweet_id"],
                tweet_fields=["created_at", "text", "referenced_tweets", "entities", "conversation_id"],
            )
            if not resp.errors and resp.includes and resp.includes.get("tweets"):
                logger.info(f"Fetched {len(resp.includes['tweets'])} tweets for user '{username}' using strategy 1.")
                return [format_tweet(t, user_id, username) for t in resp.includes["tweets"]]
        except TweepyException as e:
            logger.warning(f"Fetch strategy 1 failed for user '{username}': {e}")

        # Strategy 2: Get user's tweets excluding replies and retweets
        try:
            resp = await self.client.get_users_tweets(
                id=user_id,
                max_results=max_results,
                tweet_fields=["created_at", "text", "referenced_tweets", "entities", "conversation_id"],
                exclude=["replies", "retweets"],
            )
            if not resp.errors and resp.data:
                logger.info(f"Fetched {len(resp.data)} tweets for user '{username}' using strategy 2.")
                return [format_tweet(t, user_id, username) for t in resp.data]
        except TweepyException as e:
            logger.warning(f"Fetch strategy 2 failed for user '{username}': {e}")

        # Strategy 3: Search recent tweets from the user
        try:
            query = f"from:{username}"
            resp = await self.client.search_recent_tweets(
                query=query,
                max_results=min(100, max(10, max_results)),
                tweet_fields=["created_at", "text", "author_id", "referenced_tweets", "entities", "conversation_id"],
            )
            if not resp.errors and resp.data:
                logger.info(f"Fetched {len(resp.data)} tweets for user '{username}' using strategy 3.")
                return [format_tweet(t, t.author_id, username) for t in resp.data]
        except TweepyException as e:
            logger.warning(f"Fetch strategy 3 failed for user '{username}': {e}")

        logger.warning(f"All API fetch strategies failed for user '{username}'.")
        return None

    async def search(self, query: str, max_results: int = 10) -> Optional[List[Dict]]:
        """Search tweets based on a query.
        Args:
            query: The search query string
            max_results: The maximum number of tweets to return
        Returns:
            Optional[List[Dict]]: List of matching tweets if successful, None otherwise
        """
        try:
            tweets = await self.client.search_recent_tweets(
                query=query,
                max_results=max_results,
                tweet_fields=["created_at", "public_metrics", "context_annotations", "author_id", "referenced_tweets", "entities", "conversation_id"]
            )
            if tweets.errors:
                logger.error(f"Search API error for user '{self.get_username()}': {tweets.errors}")
                return None
            if tweets.data:
                # Need to fetch user info for each tweet to get username
                return [format_tweet(tweet) for tweet in tweets.data]
            return []
        except TweepyException as e:
            logger.error(f"Failed to search tweets with query '{query}': {e}")
            return None

    async def get_tweet(self, tweet_id: str) -> Optional[Dict]:
        """Retrieve a single tweet by its ID.

        Args:
            tweet_id: The ID of the tweet to retrieve

        Returns:
            Optional[Dict]: Tweet data if successful, None otherwise
        """
        try:
            tweet = await self.client.get_tweet(
                id=tweet_id,
                tweet_fields=["created_at", "public_metrics", "context_annotations", "author_id", "referenced_tweets", "entities", "conversation_id"]
            )
            if tweet.errors:
                logger.error(f"Get tweet API error for user '{self.get_username()}': {tweet.errors}")
                return None
            if tweet.data:
                return format_tweet(tweet.data)
            return None
        except TweepyException as e:
            logger.error(f"Failed to get tweet {tweet_id}: {str(e)}")
            return None

    async def get_following(self, user_id: str) -> Optional[List[Dict]]:
        """Get following list for a specific user.

        Args:
            user_id: The user ID to get following for

        Returns:
            Optional[List[Dict]]: List of following data if successful, None otherwise
        """
        try:
            following = await self.client.get_users_following(
                id=user_id,
                max_results=100,
                user_fields=["created_at", "description", "public_metrics"]
            )
            
            if following and following.data:
                return [
                    {
                        "id": user.id,
                        "username": user.username,
                        "name": user.name,
                        "description": user.description,
                        "public_metrics": user.public_metrics,
                    }
                    for user in following.data
                ]
            return []
        except Exception as e:
            logger.error(f"Failed to get following for user {user_id}: {str(e)}")
            return None 