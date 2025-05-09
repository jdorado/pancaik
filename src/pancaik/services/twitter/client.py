from typing import Any, Dict, List, Optional, Union

from bson import ObjectId

from ...core.connections import ConnectionHandler, TestableConnection, connection_test_handler
from . import api, direct_client


class TwitterClient(TestableConnection):
    """Base class for Twitter clients."""

    async def test_connection(self) -> Dict[str, Any]:
        """Test the connection by attempting to get profile info."""
        raise NotImplementedError("Test connection not implemented for base TwitterClient")

    def get_username(self) -> str:
        """Get the username of the authenticated client."""
        raise NotImplementedError("Get username not implemented for base TwitterClient")

    async def upload_media(self, data: bytes, filename: str = "image.jpg") -> Optional[int]:
        """Upload media to Twitter.

        Args:
            data: The binary data of the media file
            filename: The name of the file (default: image.jpg)

        Returns:
            Optional[int]: The media ID if successful, None otherwise
        """
        raise NotImplementedError("Upload media not implemented for base TwitterClient")

    async def create_tweet(self, text: str, images=None, reply_id=None, quote_id=None) -> Optional[Dict]:
        """Create a tweet with optional media, reply, or quote.

        Args:
            text: The text content of the tweet
            images: Optional image URLs or binary data
            reply_id: Optional ID of tweet to reply to
            quote_id: Optional ID of tweet to quote

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

    async def search(self, query: str) -> Optional[List[Dict]]:
        """Search tweets based on a query.

        Args:
            query: The search query string

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


class DirectTwitterClient(TwitterClient):
    """Twitter client using direct authentication."""

    def __init__(self, username: str, password: str):
        self.credentials = {"username": username, "password": password}

    def get_username(self) -> str:
        """Get the username of the authenticated client."""
        return self.credentials["username"]

    async def test_connection(self) -> Dict[str, Any]:
        """Test the connection by attempting to get own profile."""
        try:
            profile = await api.get_profile(self.credentials["username"], self.credentials)
            if profile and profile.get("id"):
                return {"success": True, "message": "Successfully retrieved profile", "data": {"profile_id": profile.get("id")}}
            return {"success": False, "message": "Failed to retrieve profile", "data": None}
        except Exception as e:
            return {"success": False, "message": f"Connection test failed: {str(e)}", "data": None}

    async def upload_media(self, data: bytes, filename: str = "image.jpg") -> Optional[int]:
        return await direct_client.upload_media(self.credentials, data, filename)

    async def create_tweet(self, text: str, images=None, reply_id=None, quote_id=None):
        return await direct_client.create_tweet(self.credentials, text, images, reply_id, quote_id)

    async def create_thread(self, texts, image_urls=None):
        return await direct_client.create_thread(self.credentials, texts, image_urls)

    async def get_latest_tweets(self, username: str, user_id: Optional[str] = None):
        return await direct_client.get_latest_tweets(self.credentials, username, user_id)

    async def search(self, query: str):
        return await direct_client.search(query, self.credentials)

    async def get_tweet(self, tweet_id: str):
        return await direct_client.get_tweet(tweet_id, self.credentials)


async def get_client(instance_id: str, connection_handler: ConnectionHandler) -> TwitterClient:
    """
    Get a Twitter client instance based on the connection type.

    Args:
        instance_id: The unique identifier of the connection to use
        connection_handler: Instance of the connection handler

    Returns:
        An instance of TwitterClient

    Raises:
        NotImplementedError: If the connection type is not supported
        ValueError: If connection is not found
    """
    # Get the connection parameters
    params = await connection_handler.get_connection(instance_id)
    if not params:
        raise ValueError(f"Connection not found: {instance_id}")

    # Get the connection type from the collection directly since params won't have it
    collection = connection_handler.get_collection()
    connection = await collection.find_one({"_id": ObjectId(instance_id)})
    connection_id = connection.get("connection_id")  # This is the type of connection

    if connection_id == "twitter_non_api":
        return DirectTwitterClient(username=params.get("username"), password=params.get("password"))

    raise NotImplementedError(f"Twitter connection type not implemented: {connection_id}")


@connection_test_handler("twitter_non_api")
async def test_twitter_connection(params: Dict[str, Any]) -> Dict[str, Any]:
    """Test handler for Twitter connections."""
    client = DirectTwitterClient(username=params.get("username"), password=params.get("password"))
    return await client.test_connection()
