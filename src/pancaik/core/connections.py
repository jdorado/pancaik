from typing import Dict, Any, Optional, Protocol, Callable
from bson import ObjectId
from pymongo.collection import Collection
from pymongo.database import Database

from .config import logger, get_config

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
    
    def __init__(self, db: Optional[Database] = None):
        """Initialize the connection handler.
        
        Args:
            db: Optional database instance. If not provided, will get from config when needed.
        """
        self._db = db
        self._registered_handlers: Dict[str, callable] = {}
        # Auto-register test handlers from registry
        self._registered_test_handlers = _connection_test_registry.copy()
        
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
            The connection parameters or None if not found
        """
        assert instance_id, "Instance ID cannot be empty"
        
        collection = self.get_collection()
        connection = await collection.find_one({"_id": ObjectId(instance_id)})
        
        if not connection:
            logger.warning(f"Connection not found: {instance_id}")
            return None
            
        return connection.get("params", {})

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
        connection = await self.get_connection(instance_id)
        if not connection:
            return {
                "success": False,
                "message": f"Connection not found: {instance_id}",
                "data": None
            }
        
        # Get the connection type and test handler
        collection = self.get_collection()
        conn_doc = await collection.find_one({"_id": ObjectId(instance_id)})
        connection_id = conn_doc.get("connection_id")
        
        if connection_id not in self._registered_test_handlers:
            return {
                "success": False,
                "message": f"No test handler registered for connection type: {connection_id}",
                "data": None
            }
            
        # Run the test handler
        test_handler = self._registered_test_handlers[connection_id]
        try:
            return await test_handler(connection)
        except Exception as e:
            logger.error(f"Error testing connection {instance_id}: {str(e)}")
            return {
                "success": False,
                "message": f"Test failed with error: {str(e)}",
                "data": None
            }

    async def create_connection(
        self, 
        connection_id: str,
        owner_id: str,
        params: Dict[str, Any]
    ) -> str:
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
        
        collection = self.get_collection()
        result = await collection.insert_one({
            "connection_id": connection_id,
            "owner_id": owner_id,
            "params": params
        })
        
        logger.info(f"Created new connection of type {connection_id} for owner {owner_id}")
        return str(result.inserted_id)
        
    async def update_connection(
        self,
        instance_id: str,
        params: Dict[str, Any]
    ) -> bool:
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
        
        collection = self.get_collection()
        result = await collection.update_one(
            {"_id": ObjectId(instance_id)},
            {"$set": {"params": params}}
        )
        
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