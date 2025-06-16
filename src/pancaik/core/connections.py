from typing import Any, Callable, Dict, Optional, Protocol, Set
import base64
import os

from bson import ObjectId
from cryptography.fernet import Fernet
from pymongo.collection import Collection
from pymongo.database import Database

from .config import get_config, logger

# Global registry for connection test handlers
_connection_test_registry: Dict[str, Callable] = {}


def connection_test_handler(connection_id: str):
    """
    Decorator to register a connection test handler.

    Args:
        connection_id: The type of connection this handler tests (e.g. 'twitter_non_api')

    Example:
        @connection_test_handler("twitter_non_api")
        async def test_twitter_connection(connection: Dict[str, Any]) -> Dict[str, Any]:
            ...
    """

    def decorator(func: Callable) -> Callable:
        _connection_test_registry[connection_id] = func
        logger.info(f"Registered connection test handler for: {connection_id}")
        return func

    return decorator


class TestableConnection(Protocol):
    """Protocol for connections that can be tested."""

    async def test_connection(self) -> Dict[str, Any]:
        """Test the connection and return test results.

        Returns:
            Dictionary containing test results with at least:
            - success: bool indicating if test passed
            - message: str with test details
            - data: Optional[Dict] with any additional test data
        """
        ...


class ConnectionHandler:
    """Handler for managing connection objects in the database."""

    # Define sensitive fields that need encryption/decryption
    SENSITIVE_FIELDS: Set[str] = {
        "password",
        "cookies", 
        "oauth_token_secret",
        "api_key",
        "api_secret",
        "access_token",
        "access_token_secret",
        "client_secret",
        "private_key",
        "auth_token",
        "session_token",
        "refresh_token",
    }

    def __init__(self, db: Optional[Database] = None):
        """Initialize the connection handler.

        Args:
            db: Optional database instance. If not provided, will get from config when needed.
        """
        self._db = db
        self._registered_handlers: Dict[str, callable] = {}
        # Auto-register test handlers from registry
        self._registered_test_handlers = _connection_test_registry.copy()
        # Initialize encryption
        self._init_encryption()

    def _init_encryption(self):
        """Initialize encryption utility."""
        key = os.environ.get("ENCRYPTION_KEY")
        if not key:
            logger.warning(
                "ENCRYPTION_KEY not set, generating a new key for this session"
            )
            key = Fernet.generate_key().decode()
        else:
            # Ensure the key is valid base64 and decodes to 32 bytes
            try:
                key_bytes = base64.urlsafe_b64decode(key)
                if len(key_bytes) != 32:
                    logger.warning(
                        f"ENCRYPTION_KEY does not decode to 32 bytes (got {len(key_bytes)} bytes), generating a new key"
                    )
                    key = Fernet.generate_key().decode()
            except Exception as e:
                logger.error(f"Error processing ENCRYPTION_KEY: {e}")
                key = Fernet.generate_key().decode()
        self._cipher_suite = Fernet(key.encode())
        logger.info("Connection handler encryption initialized")

    def _is_sensitive_field(self, key: str) -> bool:
        """Check if a field is sensitive and needs encryption."""
        return key.lower() in self.SENSITIVE_FIELDS

    def _encrypt_sensitive_fields(self, params: dict) -> dict:
        """Encrypt sensitive fields in the params dictionary."""
        encrypted_params = params.copy()
        for key, value in encrypted_params.items():
            if (
                self._is_sensitive_field(key)
                and value
                and value != "****"
            ):
                encrypted_params[key] = self._encrypt(value)
        return encrypted_params

    def _decrypt_sensitive_fields(self, params: dict) -> dict:
        """Decrypt sensitive fields in the params dictionary."""
        decrypted_params = params.copy()
        for key, value in decrypted_params.items():
            if (
                self._is_sensitive_field(key)
                and value
                and value != "****"
            ):
                try:
                    decrypted_params[key] = self._decrypt(value)
                except ValueError:
                    logger.warning(f"Failed to decrypt field {key}")
                    decrypted_params[key] = "****"
        return decrypted_params

    def _mask_sensitive_fields(self, params: dict) -> dict:
        """Remove sensitive fields for secure return."""
        masked_params = params.copy()
        for key in list(masked_params.keys()):
            if self._is_sensitive_field(key):
                del masked_params[key]
        return masked_params

    def _encrypt(self, data: str) -> str:
        """Encrypt a string."""
        if not data:
            return data
        assert isinstance(data, str), "Data to encrypt must be a string"
        return self._cipher_suite.encrypt(data.encode()).decode()

    def _decrypt(self, encrypted_data: str) -> str:
        """Decrypt a string."""
        if not encrypted_data:
            return encrypted_data
        assert isinstance(encrypted_data, str), "Data to decrypt must be a string"
        try:
            return self._cipher_suite.decrypt(encrypted_data.encode()).decode()
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            raise ValueError(f"Failed to decrypt data: {e}")

    def _ensure_db(self) -> Database:
        """Ensure we have a database connection."""
        if self._db is None:
            self._db = get_config("db")
            if self._db is None:
                raise ValueError("Database not initialized. Call init() first.")
        return self._db

    def get_collection(self) -> Collection:
        """Get the connections collection."""
        return self._ensure_db().connections

    def register_handler(self, connection_id: str, handler_func: callable) -> None:
        """
        Register a handler function for a specific connection type.

        Args:
            connection_id: The type of connection (e.g. 'twitter_non_api')
            handler_func: Function that processes the connection params
        """
        assert connection_id, "Connection type cannot be empty"
        assert callable(handler_func), "Handler must be callable"

        self._registered_handlers[connection_id] = handler_func
        logger.info(f"Registered handler for connection type: {connection_id}")

    def register_test_handler(self, connection_id: str, test_handler: callable) -> None:
        """
        Register a test handler function for a specific connection type.
        Note: This is typically not needed as handlers auto-register via @connection_test_handler.

        Args:
            connection_id: The type of connection (e.g. 'twitter_non_api')
            test_handler: Function that tests the connection
        """
        assert connection_id, "Connection type cannot be empty"
        assert callable(test_handler), "Test handler must be callable"

        self._registered_test_handlers[connection_id] = test_handler
        logger.info(f"Registered test handler for connection type: {connection_id}")

    async def get_connection(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a connection's parameters by its instance ID.

        Args:
            instance_id: The unique identifier of the connection to retrieve

        Returns:
            The connection parameters or None if not found (with sensitive fields decrypted)
        """
        assert instance_id, "Instance ID cannot be empty"

        collection = self.get_collection()
        connection = await collection.find_one({"_id": ObjectId(instance_id)})

        if not connection:
            logger.warning(f"Connection not found: {instance_id}")
            return None

        params = connection.get("params", {})
        # Decrypt sensitive fields before returning
        return self._decrypt_sensitive_fields(params)

    async def get_full_connection(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the full connection document by its instance ID.

        Args:
            instance_id: The unique identifier of the connection to retrieve

        Returns:
            The full connection document or None if not found
        """
        assert instance_id, "Instance ID cannot be empty"

        collection = self.get_collection()
        connection = await collection.find_one({"_id": ObjectId(instance_id)})

        if not connection:
            logger.warning(f"Connection not found: {instance_id}")
            return None

        return connection

    async def update_connection_metadata(self, instance_id: str, metadata: Dict[str, Any]) -> bool:
        """
        Update a connection's metadata.

        Args:
            instance_id: The unique identifier of the connection to update
            metadata: Metadata to update

        Returns:
            True if update was successful, False otherwise
        """
        assert instance_id, "Instance ID cannot be empty"
        assert isinstance(metadata, dict), "Metadata must be a dictionary"

        collection = self.get_collection()
        result = await collection.update_one({"_id": ObjectId(instance_id)}, {"$set": {"metadata": metadata}})

        success = result.modified_count > 0
        if success:
            logger.info(f"Updated connection metadata: {instance_id}")
        else:
            logger.warning(f"Failed to update connection metadata: {instance_id}")
        return success

    async def test_connection(self, instance_id: str) -> Dict[str, Any]:
        """
        Test a connection by its instance ID using the registered test handler.

        Args:
            instance_id: The unique identifier of the connection to test

        Returns:
            Dictionary containing test results with:
            - success: bool indicating if test passed
            - message: str with test details
            - data: Optional[Dict] with any additional test data
        """
        # Get connection with decrypted sensitive fields for testing
        connection = await self.get_connection(instance_id)
        if not connection:
            return {"success": False, "message": f"Connection not found: {instance_id}", "data": None}

        # Get the connection type and test handler
        collection = self.get_collection()
        conn_doc = await collection.find_one({"_id": ObjectId(instance_id)})
        connection_id = conn_doc.get("connection_id")

        if connection_id not in self._registered_test_handlers:
            return {"success": False, "message": f"No test handler registered for connection type: {connection_id}", "data": None}

        # Run the test handler with decrypted connection params
        test_handler = self._registered_test_handlers[connection_id]
        try:
            return await test_handler(connection)
        except Exception as e:
            logger.error(f"Error testing connection {instance_id}: {str(e)}")
            return {"success": False, "message": f"Test failed with error: {str(e)}", "data": None}

    async def create_connection(self, connection_id: str, owner_id: str, params: Dict[str, Any]) -> str:
        """
        Create a new connection.

        Args:
            connection_id: Type of the connection (e.g. 'twitter_non_api')
            owner_id: ID of the connection owner
            params: Connection parameters

        Returns:
            The instance_id of the created connection
        """
        assert connection_id, "Connection type cannot be empty"
        assert owner_id, "Owner ID cannot be empty"
        assert isinstance(params, dict), "Params must be a dictionary"

        # Encrypt sensitive fields before storing
        encrypted_params = self._encrypt_sensitive_fields(params)
        
        collection = self.get_collection()
        result = await collection.insert_one({"connection_id": connection_id, "owner_id": owner_id, "params": encrypted_params})

        logger.info(f"Created new connection of type {connection_id} for owner {owner_id}")
        return str(result.inserted_id)

    async def update_connection(self, instance_id: str, params: Dict[str, Any]) -> bool:
        """
        Update an existing connection's parameters.

        Args:
            instance_id: The unique identifier of the connection to update
            params: New connection parameters

        Returns:
            True if update was successful, False otherwise
        """
        assert instance_id, "Instance ID cannot be empty"
        assert isinstance(params, dict), "Params must be a dictionary"

        # Get existing connection to preserve sensitive fields if not provided or masked
        collection = self.get_collection()
        existing_connection = await collection.find_one({"_id": ObjectId(instance_id)})
        if not existing_connection:
            return False

        update_params = params.copy()
        for key, value in update_params.items():
            if self._is_sensitive_field(key):
                if value is None or value == "****" or value == "":
                    # Preserve existing encrypted value
                    if key in existing_connection.get("params", {}):
                        update_params[key] = existing_connection["params"][key]
                    else:
                        # Remove the key if it doesn't exist and no new value provided
                        del update_params[key]
                        continue
                else:
                    # Encrypt new value
                    update_params[key] = self._encrypt(value)

        result = await collection.update_one({"_id": ObjectId(instance_id)}, {"$set": {"params": update_params}})

        success = result.modified_count > 0
        if success:
            logger.info(f"Updated connection: {instance_id}")
        else:
            logger.warning(f"Failed to update connection: {instance_id}")
        return success

    async def delete_connection(self, instance_id: str) -> bool:
        """
        Delete a connection.

        Args:
            instance_id: The unique identifier of the connection to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        assert instance_id, "Instance ID cannot be empty"

        collection = self.get_collection()
        result = await collection.delete_one({"_id": ObjectId(instance_id)})

        success = result.deleted_count > 0
        if success:
            logger.info(f"Deleted connection: {instance_id}")
        else:
            logger.warning(f"Failed to delete connection: {instance_id}")
        return success
