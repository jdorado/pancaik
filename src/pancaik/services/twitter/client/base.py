from typing import Any, Dict, List, Optional, Union

from ....core.connections import TestableConnection


class TwitterClient(TestableConnection):
    """Base class for Twitter clients."""

    async def test_connection(self) -> Dict[str, Any]:
        """Test the connection by attempting to get profile info."""
        raise NotImplementedError("Test connection not implemented for base TwitterClient")

    def get_username(self) -> str:
        """Get the username of the authenticated client."""
        raise NotImplementedError("Get username not implemented for base TwitterClient")

    async def get_profile(self, username: str) -> Optional[Dict[str, Any]]:
        """Get a Twitter user's profile information.

        Args:
            username: The username to get profile for

        Returns:
            Optional[Dict[str, Any]]: Profile data if successful, None otherwise
        """
        raise NotImplementedError("Get profile not implemented for base TwitterClient")

    async def create_tweet(self, text: str, images=None, reply_id=None, quote_id=None, media_data=None) -> Optional[Dict]:
        """Create a tweet with optional media, reply, or quote.

        Args:
            text: The text content of the tweet
            images: Optional image URLs or binary data
            reply_id: Optional ID of tweet to reply to
            quote_id: Optional ID of tweet to quote
            media_data: Optional media data to attach to the tweet

        Returns:
            Optional[Dict]: Tweet data if successful, None otherwise
        """
        raise NotImplementedError("Create tweet not implemented for base TwitterClient")

    async def create_thread(self, texts: List[str], image_urls: Union[str, List[str]] = None) -> Optional[int]:
        """Create a thread of tweets.

        Args:
            texts: List of text content for each tweet in the thread
            image_urls: Optional image URLs to attach to first tweet

        Returns:
            Optional[int]: ID of first tweet if successful, None otherwise
        """
        raise NotImplementedError("Create thread not implemented for base TwitterClient")

    async def get_latest_tweets(self, username: str, user_id: Optional[str] = None) -> Optional[List[Dict]]:
        """Fetch the latest tweets for a user.

        Args:
            username: The username to fetch tweets for
            user_id: Optional user ID if already known

        Returns:
            Optional[List[Dict]]: List of tweet data if successful, None otherwise
        """
        raise NotImplementedError("Get latest tweets not implemented for base TwitterClient")

    async def search(self, query: str, **kwargs) -> Optional[List[Dict]]:
        """Search tweets based on a query.

        Args:
            query: The search query string
            **kwargs: Additional search parameters (implementation-specific)

        Returns:
            Optional[List[Dict]]: List of matching tweets if successful, None otherwise
        """
        raise NotImplementedError("Search not implemented for base TwitterClient")

    async def get_tweet(self, tweet_id: str) -> Optional[Dict]:
        """Retrieve a single tweet by its ID.

        Args:
            tweet_id: The ID of the tweet to retrieve

        Returns:
            Optional[Dict]: Tweet data if successful, None otherwise
        """
        raise NotImplementedError("Get tweet not implemented for base TwitterClient")

    async def get_following(self, user_id: Optional[str] = None, username: Optional[str] = None) -> Optional[List[Dict]]:
        """Get following list for a specific user.

        Args:
            user_id: The user ID to get following for (optional)
            username: The username to get following for (optional)

        Returns:
            Optional[List[Dict]]: List of following data if successful, None otherwise
        """
        raise NotImplementedError("Get following not implemented for base TwitterClient")

    async def get_rate_limit_status(self) -> dict:
        """
        Retrieve the current rate limit status for Twitter API endpoints.

        Returns:
            dict: A dictionary containing rate limit information for various API endpoints.
        """
        raise NotImplementedError("Get rate limit status not implemented for base TwitterClient")

    async def is_rate_limit_exceeded(self) -> dict:
        """
        Check if the rate limit for tweet creation is exceeded.

        Returns:
            dict: A dictionary with 'exceeded' boolean and 'retry_after_minutes' if exceeded.
        """
        return {"exceeded": False, "retry_after_minutes": 0} 