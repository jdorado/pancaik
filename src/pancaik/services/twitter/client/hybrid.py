"""
Hybrid Twitter client that selectively uses advanced API implementations.

This module provides a TwitterClient that wraps an existing client but overrides
specific methods to use the advanced API implementations from twitterapi.py.
"""

from typing import Any, Dict, List, Optional

from ....core.config import logger
from . import twitterapi
from .base import TwitterClient


class HybridTwitterClient(TwitterClient):
    """
    Hybrid Twitter client that selectively overrides methods with advanced API implementations.
    
    This client wraps an existing TwitterClient and overrides specific methods
    (like search) to use the advanced API while delegating other methods to the 
    underlying client.
    """

    def __init__(self, underlying_client: TwitterClient):
        """
        Initialize the hybrid client with an underlying client.
        
        Args:
            underlying_client: The base TwitterClient to wrap
        """
        self.underlying_client = underlying_client

    # Delegation methods - pass through to underlying client
    def get_username(self) -> str:
        """Get the username of the authenticated client."""
        return self.underlying_client.get_username()

    async def test_connection(self) -> Dict[str, Any]:
        """Test the connection by attempting to get profile info."""
        return await self.underlying_client.test_connection()

    async def get_profile(self, username: str) -> Optional[Dict[str, Any]]:
        """Get a Twitter user's profile information using advanced API implementation."""
        try:
            logger.info(f"Using advanced API get_profile for user: {username}")
            result = await twitterapi.get_user_info(user_name=username)
            return result
            
        except Exception as e:
            logger.error(f"Advanced API get_profile failed, falling back to underlying client: {e}")
            # Fallback to underlying client's get_profile method
            return await self.underlying_client.get_profile(username)

    async def create_tweet(self, text: str, images=None, reply_id=None, quote_id=None, media_data=None) -> Optional[Dict]:
        """Create a tweet with optional media, reply, or quote."""
        return await self.underlying_client.create_tweet(text, images, reply_id, quote_id, media_data)

    async def create_thread(self, texts: List[str], image_urls=None) -> Optional[int]:
        """Create a thread of tweets."""
        return await self.underlying_client.create_thread(texts, image_urls)

    async def get_latest_tweets(self, username: str, user_id: Optional[str] = None) -> Optional[List[Dict]]:
        """Fetch the latest tweets for a user using advanced API implementation."""
        try:
            logger.info(f"Using advanced API get_latest_tweets for user: {username}")
            result = await twitterapi.get_user_tweets(
                user_id=user_id,
                user_name=username,
                limit=20,  # Default reasonable limit
                include_replies=False
            )
            
            return result if result else None
            
        except Exception as e:
            logger.error(f"Advanced API get_latest_tweets failed, falling back to underlying client: {e}")
            # Fallback to underlying client's get_latest_tweets method
            return await self.underlying_client.get_latest_tweets(username, user_id)

    async def get_tweet(self, tweet_id: str) -> Optional[Dict]:
        """Retrieve a single tweet by its ID using advanced API implementation."""
        try:
            logger.info(f"Using advanced API get_tweet for tweet_id: {tweet_id}")
            result = await twitterapi.get_tweets_by_ids([tweet_id])
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"Advanced API get_tweet failed, falling back to underlying client: {e}")
            # Fallback to underlying client's get_tweet method
            return await self.underlying_client.get_tweet(tweet_id)

    async def get_following(self, user_id: Optional[str] = None, username: Optional[str] = None) -> Optional[List[Dict]]:
        """Get following list for a specific user using advanced API implementation."""
        if not user_id and not username:
            raise ValueError("Either user_id or username must be provided")
            
        try:
            # Try username first if available (preferred by advanced API)
            if username:
                logger.info(f"Using advanced API get_following for username: {username}")
                result = await twitterapi.get_user_followings(user_name=username)
                return result.get("followings") if result else None
            else:
                # If only user_id is provided, fall back to underlying client
                logger.info(f"Username not provided, falling back to underlying client for user_id: {user_id}")
                return await self.underlying_client.get_following(user_id, username)
            
        except Exception as e:
            logger.error(f"Advanced API get_following failed, falling back to underlying client: {e}")
            # Fallback to underlying client's get_following method
            return await self.underlying_client.get_following(user_id, username)

    async def get_rate_limit_status(self) -> dict:
        """Retrieve the current rate limit status for Twitter API endpoints."""
        return await self.underlying_client.get_rate_limit_status()

    async def is_rate_limit_exceeded(self) -> dict:
        """Check if the rate limit for tweet creation is exceeded."""
        return await self.underlying_client.is_rate_limit_exceeded()

    # Override methods - use advanced API implementations
    async def search(self, query: str, query_type: str = "Latest", limit: Optional[int] = None) -> Optional[List[Dict]]:
        """
        Search tweets using the advanced API implementation.
        
        Args:
            query: The search query string
            query_type: The query type - either "Latest" or "Top" (default: "Latest")
            limit: Maximum number of tweets to retrieve (optional)
            
        Returns:
            Optional[List[Dict]]: List of matching tweets if successful, None otherwise
        """
        try:
            logger.info(f"Using advanced API search for query: {query}")
            result = await twitterapi.advanced_search(
                query=query,
                query_type=query_type,
                limit=limit
            )
            
            if result and "tweets" in result:
                return result["tweets"]
            return None
            
        except Exception as e:
            logger.error(f"Advanced API search failed, falling back to underlying client: {e}")
            # Fallback to underlying client's search method
            return await self.underlying_client.search(query)

 