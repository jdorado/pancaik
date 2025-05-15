"""
Twitter search tools for agents.

This module provides tools for searching tweets with advanced filtering capabilities.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ...core.config import get_config, logger
from ...core.connections import ConnectionHandler
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


@tool(agents=["*"])
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
        Dictionary with filtered search results and metadata
    """
    # Preconditions
    assert data_store is not None, "data_store must be provided"
    assert twitter_connection, "Twitter connection must be provided"
    assert search_query, "Search query must be provided"
    
    # Initialize results
    results: List[Dict[str, Any]] = []
    
    try:
        # Get database instance from config
        db = get_config("db")
        if db is None:
            raise ValueError("Database not initialized in config")

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
        api_results = await twitter.search(query=full_query)

        # Process results
        if api_results:
            for tweet in api_results:
                # Store tweet in database
                await handler.insert_tweets([tweet])
                
                results.append({
                    "id": tweet.get("id"),
                    "text": tweet.get("text"),
                    "username": tweet.get("username"),
                    "created_at": tweet.get("created_at"),
                    "reply_count": tweet.get("reply_count", 0),
                    "like_count": tweet.get("like_count", 0),
                    "retweet_count": tweet.get("retweet_count", 0),
                    "quote_count": tweet.get("quote_count", 0),
                    "source": "api",
                })

        # Postconditions
        assert all(isinstance(r, dict) for r in results), "All results must be dictionaries"
        assert all("id" in r for r in results), "All results must have an ID"

        context = {"twitter_posts": results}

        return {
            "values": {
                "context": context,
                "output": context,
            }
        }

    except Exception as e:
        logger.error(f"Error searching Twitter: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "values": None
        }
