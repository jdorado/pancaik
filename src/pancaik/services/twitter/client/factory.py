import json
from typing import Any, Dict

from bson import ObjectId

from ....core.config import get_config
from ....core.connections import ConnectionHandler, connection_test_handler
from .api import ApiTwitterClient
from .base import TwitterClient
from .direct import DirectTwitterClient
from .hybrid import HybridTwitterClient


async def get_client(instance_id: str, connection_handler: ConnectionHandler, use_hybrid: bool = True) -> TwitterClient:
    """
    Get a Twitter client instance based on the connection type.

    Args:
        instance_id: The unique identifier of the connection to use
        connection_handler: Instance of the connection handler
        use_hybrid: Whether to wrap the client with HybridTwitterClient for advanced API features

    Returns:
        An instance of TwitterClient (potentially wrapped with HybridTwitterClient)

    Raises:
        NotImplementedError: If the connection type is not supported
        ValueError: If connection is not found
    """
    # Get the connection parameters (already decrypted by connection_handler)
    params = await connection_handler.get_connection(instance_id)
    if not params:
        raise ValueError(f"Connection not found: {instance_id}")

    # Get the connection type from the collection directly since params won't have it
    collection = connection_handler.get_collection()
    connection = await collection.find_one({"_id": ObjectId(instance_id)})
    connection_id = connection.get("connection_id")  # This is the type of connection

    # Create the base client
    base_client = None

    if connection_id == "twitter_non_api":
        # Parse cookies if it's a JSON string
        cookies = None
        cookies_data = params.get("cookies")
        if cookies_data:
            try:
                cookies_json = json.loads(cookies_data)
                cookies = cookies_json.get("cookies", [])
            except (json.JSONDecodeError, TypeError):
                cookies = cookies_data  # Fallback to raw data if parsing fails

        base_client = DirectTwitterClient(
            username=params.get("username"), 
            password=params.get("password"), 
            email=params.get("email"), 
            twoFactorSecret=params.get("twoFactorSecret"), 
            cookies=cookies
        )

    elif connection_id == "twitter_api":
        base_client = ApiTwitterClient(
            bearer_token=get_config("twitter_bearer_token"),
            consumer_key=get_config("twitter_consumer_key"),
            consumer_secret=get_config("twitter_consumer_secret"),
            access_token=params.get("access_token"),
            access_token_secret=params.get("access_token_secret"),
            screen_name=params.get("screen_name")
        )

    elif connection_id == "twitter_api_manual":
        base_client = ApiTwitterClient(
            bearer_token=params.get("api_key"),  # Using api_key as bearer_token
            consumer_key=params.get("api_key"),
            consumer_secret=params.get("api_secret"),
            access_token=params.get("access_token"),
            access_token_secret=params.get("access_token_secret"),
            screen_name=params.get("screen_name")
        )

    else:
        raise NotImplementedError(f"Twitter connection type not implemented: {connection_id}")

    # Wrap with HybridTwitterClient if requested and advanced API is available
    if use_hybrid and _is_advanced_api_available():
        return HybridTwitterClient(base_client)
    
    return base_client


def _is_advanced_api_available() -> bool:
    """
    Check if the advanced Twitter API is available by checking for the required API key.
    
    Returns:
        bool: True if advanced API is available, False otherwise
    """
    try:
        api_key = get_config("twitter_api_key")
        return bool(api_key)
    except Exception:
        return False


@connection_test_handler("twitter_non_api")
async def test_twitter_connection(params: Dict[str, Any]) -> Dict[str, Any]:
    """Test handler for Twitter connections."""
    # Parse cookies if it's a JSON string
    cookies = None
    cookies_data = params.get("cookies")
    if cookies_data:
        try:
            cookies_json = json.loads(cookies_data)
            cookies = cookies_json.get("cookies", [])
        except (json.JSONDecodeError, TypeError):
            cookies = None

    client = DirectTwitterClient(
        username=params.get("username"), 
        password=params.get("password"), 
        email=params.get("email"), 
        twoFactorSecret=params.get("twoFactorSecret"), 
        cookies=cookies
    )
    return await client.test_connection()


@connection_test_handler("twitter_api")
async def test_twitter_api_connection(params: Dict[str, Any]) -> Dict[str, Any]:
    """Test handler for Twitter API connections."""
    client = ApiTwitterClient(
        bearer_token=get_config("twitter_bearer_token"),
        consumer_key=get_config("twitter_consumer_key"),
        consumer_secret=get_config("twitter_consumer_secret"),
        access_token=params.get("access_token"),
        access_token_secret=params.get("access_token_secret"),
        screen_name=params.get("screen_name")
    )
    return await client.test_connection()


@connection_test_handler("twitter_api_manual")
async def test_twitter_api_manual_connection(params: Dict[str, Any]) -> Dict[str, Any]:
    """Test handler for Twitter API manual connections."""
    client = ApiTwitterClient(
        bearer_token=params.get("api_key"),  # Using api_key as bearer_token
        consumer_key=params.get("api_key"),
        consumer_secret=params.get("api_secret"),
        access_token=params.get("access_token"),
        access_token_secret=params.get("access_token_secret"),
        screen_name=params.get("screen_name")
    )
    return await client.test_connection() 