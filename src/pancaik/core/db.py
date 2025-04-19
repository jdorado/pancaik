from typing import Optional
from urllib.parse import urlparse

from motor.motor_asyncio import AsyncIOMotorClient


def init_db(connection_string: Optional[str] = None):
    """
    Initialize and return a MongoDB database instance.

    Args:
        connection_string: MongoDB connection string.
                         Example: "mongodb://localhost:27017/pancaik"
    Returns:
        The database instance
    """
    # Use default connection string if none provided
    connection_string = connection_string or "mongodb://localhost:27017/pancaik"

    # Parse the database name from the connection string
    parsed_uri = urlparse(connection_string)
    db_name = parsed_uri.path.lstrip("/") or "pancaik"

    client = AsyncIOMotorClient(connection_string)
    return client[db_name]
