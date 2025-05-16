"""
Twitter search tools for agents.

This module provides tools for searching tweets with advanced filtering capabilities.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ...core.config import get_config, logger
from ...core.connections import ConnectionHandler
from ...core.ai_logger import ai_logger
from ...tools.base import tool
from . import client as twitter_client
from .handlers import TwitterHandler


def build_search_query(
    base_query: str,
    start_date: datetime,
    end_date: datetime,
    min_replies: Optional[int] = None,
    min_likes: Optional[int] = None,
    min_retweets: Optional[int] = None,
    exclude_replies: bool = False,
) -> str:
    """
    Builds a Twitter search query with advanced operators.

    Args:
        base_query: Base search query string
        start_date: Start date for search
        end_date: End date for search
        min_replies: Minimum number of replies
        min_likes: Minimum number of likes/favorites
        min_retweets: Minimum number of retweets
        exclude_replies: Whether to exclude replies from search

    Returns:
        Complete search query with operators
    """
    operators = []
    
    # Add time range
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    operators.extend([f"until:{end_str}", f"since:{start_str}"])
    
    # Add engagement filters
    if min_replies:
        operators.append(f"min_replies:{min_replies}")
    if min_likes:
        operators.append(f"min_faves:{min_likes}")  # Twitter uses 'faves' instead of 'likes'
    if min_retweets:
        operators.append(f"min_retweets:{min_retweets}")
    
    # Add reply filter
    if exclude_replies:
        operators.append("-filter:replies")
    
    # Combine query parts
    query_parts = [base_query] + operators
    return " ".join(query_parts)


@tool()
async def twitter_search_posts(
    data_store: Dict[str, Any],
    twitter_connection: str,
    search_query: str,
    min_replies: Optional[int] = None,
    min_likes: Optional[int] = None,
    min_retweets: Optional[int] = None,
    exclude_replies: bool = True,
    days_recent: Optional[int] = 7,
) -> Dict[str, Any]:
    """
    Searches for tweets matching specified criteria with engagement and recency filters.

    Args:
        data_store: Agent's data store containing configuration and state
        twitter_connection: Twitter connection ID
        search_query: Search query string (can include Twitter search operators)
        min_replies: Minimum number of replies required
        min_likes: Minimum number of likes required
        min_retweets: Minimum number of retweets required
        exclude_replies: Whether to exclude replies from search
        days_recent: Number of days to look back (default: 7)

    Returns:
        Dictionary with filtered search results and metadata or graceful exit if no results
    """
    # Get required IDs from data_store
    agent_id = data_store.get("agent_id")
    account_id = data_store.get("config", {}).get("account_id")
    agent_name = data_store.get("config", {}).get("name")

    # Preconditions
    assert data_store is not None, "data_store must be provided"
    assert twitter_connection, "Twitter connection must be provided"
    assert search_query, "Search query must be provided"
    
    # Get database instance from config
    db = get_config("db")
    if db is None:
        ai_logger.error("Database not initialized in config", agent_id, account_id, agent_name)
        raise ValueError("Database not initialized in config")

    ai_logger.thinking(
        f"Starting Twitter search with query: {search_query}, filtering for engagement metrics: "
        f"min_replies={min_replies}, min_likes={min_likes}, min_retweets={min_retweets}",
        agent_id, account_id, agent_name
    )

    # Initialize connection handler and get Twitter client
    connection_handler = ConnectionHandler(db)
    twitter = await twitter_client.get_client(twitter_connection, connection_handler)
    
    # Initialize Twitter handler for database operations
    handler = TwitterHandler()
    
    # Set up date filtering
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days_recent or 7)
    
    # Build query with all operators
    full_query = build_search_query(
        search_query,
        start_date,
        end_date,
        min_replies=min_replies,
        min_likes=min_likes,
        min_retweets=min_retweets,
        exclude_replies=exclude_replies
    )

    # Search using Twitter API
    logger.info(f"Searching Twitter with query: {full_query}")
    ai_logger.action(f"Executing Twitter search with full query: {full_query}", agent_id, account_id, agent_name)
    api_results = await twitter.search(query=full_query)

    # Return early with graceful exit if no results found
    if not api_results:
        ai_logger.result("No tweets found matching the search criteria", agent_id, account_id, agent_name)
        return {
            "should_exit": True  # Signal graceful exit
        }

    # Process results
    # Get tweet IDs to check which ones already exist
    tweet_ids = [tweet["_id"] for tweet in api_results]
    existing_ids = await handler.get_existing_tweet_ids(tweet_ids)
    
    # Filter out tweets that don't exist in the database
    new_tweets = [tweet for tweet in api_results if tweet["_id"] not in existing_ids]
    
    # Insert only new tweets into database
    if new_tweets:
        await handler.insert_tweets(new_tweets)
    
    ai_logger.result(
        f"Successfully processed search results: found {len(api_results)} tweets",
        agent_id, account_id, agent_name
    )

    # Postconditions
    assert all(isinstance(r, dict) for r in api_results), "All results must be dictionaries"
    assert all("_id" in r for r in api_results), "All results must have an ID"

    context = {"twitter_posts": api_results}

    return {
        "values": {
            "context": context,
            "output": context,
        }
    }
