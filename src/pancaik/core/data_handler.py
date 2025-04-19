"""
Generic database handler for persisting and caching data with timestamps.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from .config import get_config, logger


class DataHandler:
    """Handler for generic data caching and persistence operations."""

    def __init__(self, collection_name: str = "data_cache"):
        """Initialize the Data handler.

        Args:
            collection_name: The name of the MongoDB collection to use.
                             Defaults to "data_cache".
        """
        self.db = get_config("db")
        assert self.db is not None, "Database must be initialized"

        assert collection_name, "Collection name must be provided"
        self._collection_name = collection_name
        logger.debug(f"DataHandler initialized for collection: {self._collection_name}")

    def get_collection(self):
        """Get the data cache collection from the database."""
        collection = self.db[self._collection_name]
        # Optional: Add index creation here if needed, e.g., on 'last_updated'
        # collection.create_index([("last_updated", -1)])
        return collection

    async def get_data_by_key(self, data_key: str) -> Optional[Dict[str, Any]]:
        """Get data from the database by its unique key."""
        assert data_key, "Data key must not be empty"
        collection = self.get_collection()
        logger.debug(f"Attempting to fetch data with key: {data_key} from {self._collection_name}")
        result = await collection.find_one({"_id": data_key})
        if result:
            logger.debug(f"Found data for key: {data_key} in {self._collection_name}")
        else:
            logger.debug(f"No data found for key: {data_key} in {self._collection_name}")
        return result

    async def get_data_by_keys(self, data_keys: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get multiple data entries from the database by their unique keys.

        Args:
            data_keys: A list of data keys to fetch.

        Returns:
            A dictionary mapping found data keys to their corresponding documents.
        """
        assert data_keys is not None, "Data keys list must be provided"
        if not data_keys:  # Handle empty list case
            return {}

        collection = self.get_collection()
        logger.debug(f"Attempting to fetch data for {len(data_keys)} keys from {self._collection_name}.")
        cursor = collection.find({"_id": {"$in": data_keys}})
        results = await cursor.to_list(length=len(data_keys))

        # Convert list of results to a dictionary keyed by _id for easy lookup
        results_dict = {doc["_id"]: doc for doc in results}

        found_keys = len(results_dict)
        if found_keys > 0:
            logger.debug(f"Found {found_keys} data entries out of {len(data_keys)} requested from {self._collection_name}.")
        else:
            logger.debug(f"No data entries found for the requested keys in {self._collection_name}.")

        return results_dict

    async def save_data(self, data_key: str, content: Any, timestamp: datetime) -> bool:
        """Save or update data in the database."""
        assert data_key, "Data key must not be empty"
        assert content is not None, "Content must not be None"
        assert timestamp, "Timestamp must be provided"

        collection = self.get_collection()
        document = {"_id": data_key, "content": content, "last_updated": timestamp}
        logger.debug(f"Saving data with key: {data_key} to {self._collection_name}")
        try:
            result = await collection.replace_one({"_id": data_key}, document, upsert=True)
            if result.acknowledged:
                logger.info(f"Successfully saved/updated data for key: {data_key} in {self._collection_name}")
                return True
            else:
                logger.warning(f"Save operation not acknowledged for key: {data_key} in {self._collection_name}")
                return False
        except Exception as e:
            logger.error(f"Error saving data for key {data_key} in {self._collection_name}: {e}")
            return False
