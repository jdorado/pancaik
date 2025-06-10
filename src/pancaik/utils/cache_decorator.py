"""
Generic caching decorator with expiration for async functions.

This module provides a decorator that caches function results in the database
with configurable expiration times.
"""

import hashlib
import json
import pickle
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Optional

from ..core.config import logger
from ..core.data_handler import DataHandler


def cache_with_expiration(
    expiration_minutes: int = 5,
    collection_name: str = "function_cache",
    cache_key_prefix: Optional[str] = None,
    exclude_params: Optional[list] = None,
):
    """
    Decorator that caches async function results with expiration.

    Args:
        expiration_minutes: Cache expiration time in minutes (default: 5)
        collection_name: MongoDB collection name for cache storage (default: "function_cache")
        cache_key_prefix: Optional prefix for cache keys (default: function name)
        exclude_params: List of parameter names to exclude from cache key generation

    Note:
        If a 'data_store' parameter is present and contains config.account_id,
        it will be automatically included in the cache key for multi-tenant isolation.
        Cache key format: function_name:account_id:parameter_hash (when account_id available)
        or function_name:parameter_hash (when account_id not available)

    Usage:
        @cache_with_expiration(expiration_minutes=60)
        async def my_function(param1, param2):
            # expensive operation
            return result
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Initialize data handler for caching
            data_handler = DataHandler(collection_name=collection_name)

            # Generate cache key from function inputs
            cache_key = _generate_cache_key(func, args, kwargs, cache_key_prefix, exclude_params)

            # Check if cached result exists and is not expired
            cached_data = await data_handler.get_data_by_key(cache_key)

            if cached_data:
                cached_time = cached_data.get("last_updated")
                if cached_time and _is_cache_valid(cached_time, expiration_minutes):
                    logger.debug(f"Cache hit for function {func.__name__} with key: {cache_key}")
                    # Deserialize and return cached result
                    return _deserialize_result(cached_data.get("content"))
                else:
                    logger.debug(f"Cache expired for function {func.__name__} with key: {cache_key}")
            else:
                logger.debug(f"Cache miss for function {func.__name__} with key: {cache_key}")

            # Execute the original function
            result = await func(*args, **kwargs)

            # Cache the result
            current_time = datetime.utcnow()
            serialized_result = _serialize_result(result)

            success = await data_handler.save_data(data_key=cache_key, content=serialized_result, timestamp=current_time)

            if success:
                logger.debug(f"Cached result for function {func.__name__} with key: {cache_key}")
            else:
                logger.warning(f"Failed to cache result for function {func.__name__} with key: {cache_key}")

            return result

        return wrapper

    return decorator


def _generate_cache_key(
    func: Callable, args: tuple, kwargs: dict, cache_key_prefix: Optional[str] = None, exclude_params: Optional[list] = None
) -> str:
    """
    Generate a unique cache key from function name and parameters.

    Args:
        func: The function being cached
        args: Positional arguments
        kwargs: Keyword arguments
        cache_key_prefix: Optional prefix for the cache key
        exclude_params: List of parameter names to exclude from key generation

    Returns:
        A unique cache key string
    """
    # Use function name as base or custom prefix
    prefix = cache_key_prefix or func.__name__

    # Extract account_id from data_store if present
    account_id = None

    # Check if data_store is in kwargs
    if "data_store" in kwargs and isinstance(kwargs["data_store"], dict):
        config = kwargs["data_store"].get("config", {})
        account_id = config.get("account_id")
    else:
        # Check if data_store is in args by mapping to parameter names
        import inspect

        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())

        for i, arg in enumerate(args):
            if i < len(param_names) and param_names[i] == "data_store":
                if isinstance(arg, dict):
                    config = arg.get("config", {})
                    account_id = config.get("account_id")
                break

    # Filter out excluded parameters
    if exclude_params:
        # Get function parameter names to map args to kwargs
        import inspect

        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())

        # Convert args to kwargs for easier filtering
        args_as_kwargs = {}
        for i, arg in enumerate(args):
            if i < len(param_names):
                param_name = param_names[i]
                if param_name not in exclude_params:
                    args_as_kwargs[param_name] = arg

        # Filter kwargs
        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in exclude_params}

        # Combine filtered parameters
        all_params = {**args_as_kwargs, **filtered_kwargs}
    else:
        # Convert all args to a consistent format
        import inspect

        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())

        args_as_kwargs = {}
        for i, arg in enumerate(args):
            if i < len(param_names):
                args_as_kwargs[param_names[i]] = arg

        all_params = {**args_as_kwargs, **kwargs}

    # Create a deterministic string representation
    try:
        # Sort parameters for consistent ordering
        sorted_params = dict(sorted(all_params.items()))
        params_str = json.dumps(sorted_params, sort_keys=True, default=str)
    except (TypeError, ValueError):
        # Fallback for non-JSON-serializable objects
        params_str = str(sorted_params)

    # Create hash of the parameters
    params_hash = hashlib.sha256(params_str.encode()).hexdigest()[:16]

    # Include account_id in the cache key if available
    if account_id:
        return f"{prefix}:{account_id}:{params_hash}"
    else:
        return f"{prefix}:{params_hash}"


def _is_cache_valid(cached_time: datetime, expiration_minutes: int) -> bool:
    """
    Check if cached data is still valid based on expiration time.

    Args:
        cached_time: When the data was cached
        expiration_minutes: Cache expiration time in minutes

    Returns:
        True if cache is still valid, False otherwise
    """
    if not isinstance(cached_time, datetime):
        return False

    expiration_time = cached_time + timedelta(minutes=expiration_minutes)
    return datetime.utcnow() < expiration_time


def _serialize_result(result: Any) -> Any:
    """
    Serialize the result for storage.

    For simple types (dict, list, str, int, float, bool), store as-is.
    For complex types, use pickle serialization.

    Args:
        result: The result to serialize

    Returns:
        Serialized result
    """
    # Check if result is a simple JSON-serializable type
    simple_types = (dict, list, str, int, float, bool, type(None))

    if isinstance(result, simple_types):
        try:
            # Test JSON serialization
            json.dumps(result, default=str)
            return {"type": "json", "data": result}
        except (TypeError, ValueError):
            pass

    # Use pickle for complex objects
    try:
        pickled_data = pickle.dumps(result)
        return {"type": "pickle", "data": pickled_data}
    except Exception as e:
        logger.warning(f"Failed to serialize result: {e}")
        return {"type": "string", "data": str(result)}


def _deserialize_result(serialized_data: Any) -> Any:
    """
    Deserialize the cached result.

    Args:
        serialized_data: The serialized data from cache

    Returns:
        Deserialized result
    """
    if not isinstance(serialized_data, dict) or "type" not in serialized_data:
        # Legacy format or simple data
        return serialized_data

    data_type = serialized_data.get("type")
    data = serialized_data.get("data")

    if data_type == "json":
        return data
    elif data_type == "pickle":
        try:
            return pickle.loads(data)
        except Exception as e:
            logger.warning(f"Failed to deserialize pickled data: {e}")
            return None
    elif data_type == "string":
        return data
    else:
        logger.warning(f"Unknown serialization type: {data_type}")
        return data


async def clear_cache(
    collection_name: str = "function_cache",
    function_name: Optional[str] = None,
    account_id: Optional[str] = None,
    older_than_minutes: Optional[int] = None,
):
    """
    Utility function to clear cached data.

    Args:
        collection_name: The cache collection to clear
        function_name: If provided, only clear cache for this function
        account_id: If provided, only clear cache for this account
        older_than_minutes: If provided, only clear cache older than this many minutes
    """
    data_handler = DataHandler(collection_name=collection_name)
    collection = data_handler.get_collection()

    # Build query filter
    query_filter = {}

    if function_name and account_id:
        # Match cache keys that start with function_name:account_id:
        query_filter["_id"] = {"$regex": f"^{function_name}:{account_id}:"}
    elif function_name:
        # Match cache keys that start with the function name
        query_filter["_id"] = {"$regex": f"^{function_name}:"}
    elif account_id:
        # Match cache keys that contain the account_id
        query_filter["_id"] = {"$regex": f":{account_id}:"}

    if older_than_minutes:
        cutoff_time = datetime.utcnow() - timedelta(minutes=older_than_minutes)
        query_filter["last_updated"] = {"$lt": cutoff_time}

    try:
        result = await collection.delete_many(query_filter)
        logger.info(f"Cleared {result.deleted_count} cache entries from {collection_name}")
        return result.deleted_count
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        return 0
