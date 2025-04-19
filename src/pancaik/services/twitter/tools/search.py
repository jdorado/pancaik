"""
Twitter search tools for agents.

This module provides tools for searching tweets.
"""

from typing import Any, Dict

from ....tools.base import tool
from .. import client


@tool
async def search_tweets(query: str, data_store: Dict[str, Any]):
    """
    Searches for tweets matching a query string.

    Args:
        query: Search query string
        data_store: Agent's data store containing configuration and state

    Returns:
        Dictionary with search results
    """
    # Preconditions
    assert query, "Search query must be provided"

    results = []

    # Extract required configuration from data_store
    credentials = data_store.get("config", {}).get("twitter", {}).get("credentials", {})
    assert credentials, "Twitter credentials must be in the agent's data store"

    # Search in Twitter API
    api_results = await client.search(query, credentials)
    if api_results:
        for tweet in api_results:
            results.append(
                {
                    "id": tweet.get("_id"),
                    "text": tweet.get("text"),
                    "username": tweet.get("username"),
                    "created_at": tweet.get("created_at"),
                    "source": "api",
                }
            )

    return {
        "status": "success" if results else "no_results",
        "query": query,
        "count": len(results),
        "results": results,
        "values": (
            {
                "twitter_search_query": query,
                "twitter_search_results_count": len(results),
                "twitter_search_results": results if results else [],
            }
            if results
            else None
        ),
    }
