"""
HubSpot Cache Management

This module provides caching functionality for HubSpot metadata, primarily deal pipelines
and their stages. The cache is stored in the connection metadata with configurable expiration.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from ...core.config import logger
from ...core.connections import ConnectionHandler
from .hubspot_client import HubspotClient


async def load_and_cache_hubspot_metadata(
    connection_handler: ConnectionHandler, connection_id: str, force_refresh: bool = False, cache_expiry_days: int = 7
) -> Dict[str, Any]:
    """
    Load HubSpot metadata (deal pipelines and stages) and cache it in the connection.

    Args:
        connection_handler: Database connection handler
        connection_id: HubSpot connection ID
        force_refresh: Force refresh even if cache is valid
        cache_expiry_days: Days before cache expires (default: 7 days)

    Returns:
        Dictionary with cached metadata
    """
    logger.info(f"Loading HubSpot metadata for connection {connection_id}")

    connection_doc = await connection_handler.get_full_connection(connection_id)
    if not connection_doc:
        raise ValueError(f"Connection not found: {connection_id}")

    metadata = connection_doc.get("metadata", {})
    cache_timestamp = metadata.get("cache_timestamp")

    if not force_refresh and cache_timestamp:
        try:
            cached_time = datetime.fromisoformat(cache_timestamp.replace("Z", "+00:00"))
            expiry_time = cached_time + timedelta(days=cache_expiry_days)

            if datetime.now(timezone.utc) < expiry_time:
                logger.info(f"Using cached HubSpot metadata for connection {connection_id} (expires: {expiry_time.isoformat()})")
                return metadata.get("hubspot_cache", {})
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid cache timestamp for HubSpot, refreshing: {e}")

    logger.info(f"Refreshing HubSpot metadata cache for connection {connection_id}")

    client = await HubspotClient.create(connection_id=connection_id, connection_handler=connection_handler)
    try:
        pipelines_data = await client.get_deal_pipelines()

        cache_data = {"deal_pipelines": pipelines_data.get("results", [])}

        cache_metadata = {
            "hubspot_cache": cache_data,
            "cache_timestamp": datetime.now(timezone.utc).isoformat(),
            "cache_expiry_days": cache_expiry_days,
            "cache_expires_at": (datetime.now(timezone.utc) + timedelta(days=cache_expiry_days)).isoformat(),
            "cache_items_count": {"deal_pipelines": len(cache_data["deal_pipelines"])},
        }

        updated_metadata = {**metadata, **cache_metadata}
        await connection_handler.update_connection_metadata(connection_id, updated_metadata)

        logger.info(f"HubSpot metadata cached successfully for connection {connection_id}")
        logger.debug(f"Cached items: {cache_metadata['cache_items_count']}")

        return cache_data

    except Exception as e:
        logger.error(f"Failed to load HubSpot metadata for connection {connection_id}: {str(e)}")
        return metadata.get("hubspot_cache", {})
    finally:
        client.close()


async def get_cached_hubspot_metadata(connection_handler: ConnectionHandler, connection_id: str) -> Dict[str, Any]:
    """
    Get cached HubSpot metadata from connection.

    Args:
        connection_handler: Database connection handler
        connection_id: HubSpot connection ID

    Returns:
        Cached metadata or empty dict
    """
    connection_doc = await connection_handler.get_full_connection(connection_id)
    if not connection_doc:
        return {}

    metadata = connection_doc.get("metadata", {})
    return metadata.get("hubspot_cache", {})


def find_pipeline_by_name(pipelines: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    """
    Helper to find a pipeline by its label (name) in cached data.

    Args:
        pipelines: List of pipeline objects.
        name: The label to search for (case-insensitive).

    Returns:
        The found pipeline or an empty dict.
    """
    if not pipelines or not name:
        return {}
    name_lower = name.lower()
    for pipeline in pipelines:
        if pipeline.get("label", "").lower() == name_lower:
            return pipeline
    return {}


def find_stage_by_name(pipeline: Dict[str, Any], stage_name: str) -> Dict[str, Any]:
    """
    Helper to find a stage by its label (name) within a specific pipeline.

    Args:
        pipeline: The pipeline object containing stages.
        stage_name: The stage label to search for (case-insensitive).

    Returns:
        The found stage or an empty dict.
    """
    if not pipeline or not stage_name:
        return {}
    stage_name_lower = stage_name.lower()
    for stage in pipeline.get("stages", []):
        if stage.get("label", "").lower() == stage_name_lower:
            return stage
    return {}


def simplify_hubspot_metadata(cached_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simplifies HubSpot metadata for LLM prompt.

    Extracts key information about deal pipelines and their stages to provide
    as context to the language model.

    Args:
        cached_metadata: The cached data from HubSpot, typically containing deal_pipelines.

    Returns:
        A simplified dictionary with deal pipeline information.
    """
    simplified = {}
    if "deal_pipelines" in cached_metadata:
        simplified["deal_pipelines"] = []
        for pipeline in cached_metadata.get("deal_pipelines", []):
            simplified_pipeline = {
                "id": pipeline.get("id"),
                "label": pipeline.get("label"),
                "stages": [
                    {"id": stage.get("id"), "label": stage.get("label")} for stage in pipeline.get("stages", [])
                ],
            }
            simplified["deal_pipelines"].append(simplified_pipeline)
    return simplified 