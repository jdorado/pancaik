import json
from typing import Any, Dict

from bson import ObjectId

from ....core.config import get_config
from ....core.connections import ConnectionHandler, connection_test_handler
from ....utils.encryption import encryption_util
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
    # Get the connection parameters
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
        # Decrypt the password before creating the client
        username = params.get("username")
        encrypted_password = params.get("password")
        email = params.get("email")  # Email doesn't need decryption
        encrypted_twoFactorSecret = params.get("twoFactorSecret")
        encrypted_cookies = params.get("cookies")

        # Decrypt the password if it exists
        password = encryption_util.decrypt(encrypted_password) if encrypted_password else None
        # Decrypt the twoFactorSecret if it exists
        twoFactorSecret = encryption_util.decrypt(encrypted_twoFactorSecret) if encrypted_twoFactorSecret else None
        # Decrypt the cookies if it exists and parse JSON to extract cookies array
        cookies = None
        if encrypted_cookies:
            decrypted_cookies = encryption_util.decrypt(encrypted_cookies)
            try:
                cookies_json = json.loads(decrypted_cookies)
                cookies = cookies_json.get("cookies", [])
            except (json.JSONDecodeError, TypeError):
                cookies = decrypted_cookies  # Fallback to raw string if parsing fails

        base_client = DirectTwitterClient(username=username, password=password, email=email, twoFactorSecret=twoFactorSecret, cookies=cookies)

    elif connection_id == "twitter_api":
        # Get API credentials from config and database
        encrypted_access_token = params.get("access_token")
        encrypted_access_token_secret = params.get("access_token_secret")
        screen_name = params.get("screen_name")  # Get screen_name from connection
        
        # Get credentials from global config
        bearer_token = get_config("twitter_bearer_token")
        consumer_key = get_config("twitter_consumer_key")
        consumer_secret = get_config("twitter_consumer_secret")

        # Decrypt the access token credentials if they exist
        access_token = encryption_util.decrypt(encrypted_access_token) if encrypted_access_token else None
        access_token_secret = encryption_util.decrypt(encrypted_access_token_secret) if encrypted_access_token_secret else None

        base_client = ApiTwitterClient(
            bearer_token=bearer_token,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
            screen_name=screen_name
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
    # Decrypt the password before creating the client for testing
    username = params.get("username")
    encrypted_password = params.get("password")
    email = params.get("email")  # Email doesn't need decryption
    encrypted_twoFactorSecret = params.get("twoFactorSecret")
    encrypted_cookies = params.get("cookies")

    # Decrypt the password if it exists
    password = encryption_util.decrypt(encrypted_password) if encrypted_password else None
    # Decrypt the twoFactorSecret if it exists
    twoFactorSecret = encryption_util.decrypt(encrypted_twoFactorSecret) if encrypted_twoFactorSecret else None
    # Decrypt the cookies if it exists and parse JSON to extract cookies array
    cookies = None
    if encrypted_cookies:
        decrypted_cookies = encryption_util.decrypt(encrypted_cookies)
        try:
            cookies_json = json.loads(decrypted_cookies)
            cookies = cookies_json.get("cookies", [])
        except (json.JSONDecodeError, TypeError):
            cookies = None

    # Format cookies

    client = DirectTwitterClient(username=username, password=password, email=email, twoFactorSecret=twoFactorSecret, cookies=cookies)
    return await client.test_connection()


@connection_test_handler("twitter_api")
async def test_twitter_api_connection(params: Dict[str, Any]) -> Dict[str, Any]:
    """Test handler for Twitter API connections."""
    # Get API credentials from config and database
    encrypted_access_token = params.get("access_token")
    encrypted_access_token_secret = params.get("access_token_secret")
    screen_name = params.get("screen_name")  # Get screen_name from connection
    
    # Get credentials from global config
    bearer_token = get_config("twitter_bearer_token")
    consumer_key = get_config("twitter_consumer_key")
    consumer_secret = get_config("twitter_consumer_secret")

    # Decrypt the access token credentials if they exist
    access_token = encryption_util.decrypt(encrypted_access_token) if encrypted_access_token else None
    access_token_secret = encryption_util.decrypt(encrypted_access_token_secret) if encrypted_access_token_secret else None

    client = ApiTwitterClient(
        bearer_token=bearer_token,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
        screen_name=screen_name
    )
    return await client.test_connection() 