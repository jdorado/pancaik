"""
Pipedrive Cache Management

This module provides caching functionality for Pipedrive metadata including pipelines, 
stages, and users. The cache is stored in the connection metadata with configurable expiration.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta

from ...core.config import logger
from ...core.connections import ConnectionHandler
from .pipedrive_client import PipedriveClient


async def load_and_cache_pipedrive_metadata(
    connection_handler: ConnectionHandler,
    connection_id: str,
    api_token: str,
    force_refresh: bool = False,
    cache_expiry_days: int = 7
) -> Dict[str, Any]:
    """
    Load Pipedrive metadata (pipelines, stages, users, etc.) and cache it in the connection.
    
    Args:
        connection_handler: Database connection handler
        connection_id: Pipedrive connection ID
        api_token: Pipedrive API token
        force_refresh: Force refresh even if cache is valid
        cache_expiry_days: Days before cache expires (default: 7 days)
        
    Returns:
        Dictionary with cached metadata
    """
    logger.info(f"Loading Pipedrive metadata for connection {connection_id}")
    
    # Get current connection to check existing cache
    connection_doc = await connection_handler.get_full_connection(connection_id)
    if not connection_doc:
        raise ValueError(f"Connection not found: {connection_id}")
    
    # Check if we have valid cached data
    metadata = connection_doc.get('metadata', {})
    cache_timestamp = metadata.get('cache_timestamp')
    
    if not force_refresh and cache_timestamp:
        try:
            cached_time = datetime.fromisoformat(cache_timestamp.replace('Z', '+00:00'))
            expiry_time = cached_time + timedelta(days=cache_expiry_days)
            
            if datetime.now(timezone.utc) < expiry_time:
                logger.info(f"Using cached metadata for connection {connection_id} (expires: {expiry_time.isoformat()})")
                return metadata.get('pipedrive_cache', {})
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid cache timestamp, refreshing: {e}")
    
    # Cache is expired or doesn't exist, refresh it
    logger.info(f"Refreshing Pipedrive metadata cache for connection {connection_id}")
    
    with PipedriveClient(api_token=api_token) as client:
        try:
            # Load essential cache data
            # TODO blocking fix
            cache_data = client.get_essential_cache_data()
            
            # Add timestamp and expiry info
            cache_metadata = {
                'pipedrive_cache': cache_data,
                'cache_timestamp': datetime.now(timezone.utc).isoformat(),
                'cache_expiry_days': cache_expiry_days,
                'cache_expires_at': (datetime.now(timezone.utc) + timedelta(days=cache_expiry_days)).isoformat(),
                'cache_items_count': {
                    key: len(value) if isinstance(value, list) else 1 
                    for key, value in cache_data.items()
                }
            }
            
            # Update connection metadata
            updated_metadata = {**metadata, **cache_metadata}
            await connection_handler.update_connection_metadata(connection_id, updated_metadata)
            
            logger.info(f"Pipedrive metadata cached successfully for connection {connection_id}")
            logger.debug(f"Cached items: {cache_metadata['cache_items_count']}")
            
            return cache_data
            
        except Exception as e:
            logger.error(f"Failed to load Pipedrive metadata for connection {connection_id}: {str(e)}")
            # Return any existing cache data as fallback
            return metadata.get('pipedrive_cache', {})


async def get_cached_pipedrive_metadata(
    connection_handler: ConnectionHandler,
    connection_id: str,
    item_type: str = None
) -> Dict[str, Any]:
    """
    Get cached Pipedrive metadata from connection.
    
    Args:
        connection_handler: Database connection handler
        connection_id: Pipedrive connection ID
        item_type: Specific type to retrieve (pipelines, stages, users)
        
    Returns:
        Cached metadata or empty dict
    """
    connection_doc = await connection_handler.get_full_connection(connection_id)
    if not connection_doc:
        return {}
    
    metadata = connection_doc.get('metadata', {})
    cache_data = metadata.get('pipedrive_cache', {})
    
    if item_type:
        return cache_data.get(item_type, [])
    
    return cache_data


async def refresh_pipedrive_cache(
    connection_handler: ConnectionHandler,
    connection_id: str,
    api_token: str
) -> Dict[str, Any]:
    """
    Force refresh the Pipedrive metadata cache.
    
    Args:
        connection_handler: Database connection handler
        connection_id: Pipedrive connection ID
        api_token: Pipedrive API token
        
    Returns:
        Dictionary with refreshed cached metadata
    """
    return await load_and_cache_pipedrive_metadata(
        connection_handler=connection_handler,
        connection_id=connection_id,
        api_token=api_token,
        force_refresh=True
    )


def find_item_by_name(items: list, name: str, name_field: str = 'name') -> Dict[str, Any]:
    """
    Helper function to find an item by name in cached data.
    
    Args:
        items: List of items to search
        name: Name to search for (case-insensitive)
        name_field: Field name to search in (default: 'name')
        
    Returns:
        Found item or empty dict
    """
    if not items or not name:
        return {}
    
    name_lower = name.lower()
    for item in items:
        if isinstance(item, dict) and item.get(name_field, '').lower() == name_lower:
            return item
    
    return {}


def find_item_by_id(items: list, item_id: int) -> Dict[str, Any]:
    """
    Helper function to find an item by ID in cached data.
    
    Args:
        items: List of items to search
        item_id: ID to search for
        
    Returns:
        Found item or empty dict
    """
    if not items or not item_id:
        return {}
    
    for item in items:
        if isinstance(item, dict) and item.get('id') == item_id:
            return item
    
    return {}


def find_stage_by_name(stages: list, stage_name: str, pipeline_name: str = None, pipelines: list = None) -> Dict[str, Any]:
    """
    Helper function to find a stage by name, optionally within a specific pipeline.
    
    Args:
        stages: List of stages
        stage_name: Stage name to find
        pipeline_name: Optional pipeline name to filter by
        pipelines: List of pipelines (needed if pipeline_name provided)
        
    Returns:
        Found stage or empty dict
    """
    if not stages or not stage_name:
        return {}
    
    # If pipeline name specified, filter stages by pipeline
    if pipeline_name and pipelines:
        pipeline = find_item_by_name(pipelines, pipeline_name)
        if pipeline:
            pipeline_id = pipeline.get('id')
            stages = [s for s in stages if s.get('pipeline_id') == pipeline_id]
    
    return find_item_by_name(stages, stage_name)


def find_user_by_email(users: list, email: str) -> Dict[str, Any]:
    """
    Helper function to find a user by email in cached data.
    
    Args:
        users: List of users
        email: Email to search for (case-insensitive)
        
    Returns:
        Found user or empty dict
    """
    return find_item_by_name(users, email, 'email')


def get_pipeline_stages(stages: list, pipeline_id: int) -> List[Dict[str, Any]]:
    """
    Get all stages for a specific pipeline.
    
    Args:
        stages: List of all stages
        pipeline_id: Pipeline ID to filter by
        
    Returns:
        List of stages for the pipeline
    """
    if not stages or not pipeline_id:
        return []
    
    return [s for s in stages if s.get('pipeline_id') == pipeline_id]


def simplify_pipedrive_metadata(cached_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simplify cached Pipedrive metadata structure for LLM consumption.
    
    This function restructures the cached data to make it easier for LLMs to understand:
    - Groups pipelines by name with simplified stage information
    - Simplifies users to just id, name, email
    - Preserves other metadata fields as-is
    
    Args:
        cached_metadata: Raw cached Pipedrive metadata
        
    Returns:
        Simplified metadata dictionary optimized for LLM processing
    """
    simplified_metadata = {}
    
    # Group pipelines by name with simplified stage information
    if 'pipelines' in cached_metadata and 'stages' in cached_metadata:
        pipelines = cached_metadata.get('pipelines', [])
        stages = cached_metadata.get('stages', [])
        
        # Create a mapping of stage_id to stage info for quick lookup
        stage_lookup = {stage['id']: stage for stage in stages}
        
        simplified_pipelines = {}
        for pipeline in pipelines:
            pipeline_name = pipeline.get('name', f"Pipeline {pipeline.get('id')}")
            pipeline_id = pipeline.get('id')
            
            # Get stages for this pipeline and sort by order_nr
            pipeline_stages = [
                stage for stage in stages 
                if stage.get('pipeline_id') == pipeline_id
            ]
            pipeline_stages.sort(key=lambda x: x.get('order_nr', 0))
            
            # Simplify stage information
            simplified_stages = [
                {
                    'id': stage.get('id'),
                    'name': stage.get('name'),
                    'order': stage.get('order_nr', 0)
                }
                for stage in pipeline_stages
            ]
            
            simplified_pipelines[pipeline_name] = {
                'id': pipeline_id,
                'stages': simplified_stages
            }
        
        simplified_metadata['pipelines'] = simplified_pipelines
    
    # Simplify users to just id, name, email
    if 'users' in cached_metadata:
        users = cached_metadata.get('users', [])
        simplified_users = [
            {
                'id': user.get('id'),
                'name': user.get('name'),
                'email': user.get('email')
            }
            for user in users
            if user.get('id')  # Only include users with valid IDs
        ]
        simplified_metadata['users'] = simplified_users
    
    # Keep other metadata as-is for now (can be simplified later if needed)
    for key in ['deal_fields', 'person_fields', 'organization_fields']:
        if key in cached_metadata:
            simplified_metadata[key] = cached_metadata[key]
    
    return simplified_metadata


def get_cache_summary(cache_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a summary of cached data for debugging/monitoring.
    
    Args:
        cache_data: Cached Pipedrive metadata
        
    Returns:
        Summary dictionary with counts and timestamps
    """
    summary = {
        'cached_items': {},
        'total_items': 0,
        'cache_timestamp': cache_data.get('cache_timestamp'),
        'cache_expires_at': cache_data.get('cache_expires_at'),
        'is_expired': False
    }
    
    # Count items in each category
    for key, value in cache_data.items():
        if key not in ['cache_timestamp', 'cache_expiry_days', 'cache_expires_at', 'cache_items_count']:
            if isinstance(value, list):
                count = len(value)
                summary['cached_items'][key] = count
                summary['total_items'] += count
            else:
                summary['cached_items'][key] = 1
                summary['total_items'] += 1
    
    # Check if cache is expired
    expires_at = cache_data.get('cache_expires_at')
    if expires_at:
        try:
            expiry_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            summary['is_expired'] = datetime.now(timezone.utc) > expiry_time
        except (ValueError, TypeError):
            summary['is_expired'] = True
    
    return summary 