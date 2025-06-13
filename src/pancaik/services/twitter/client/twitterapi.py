import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from pancaik.core.config import logger, get_config
from pancaik.services.twitter.models import format_tweet, format_profile


async def _make_twitter_api_request(
    url: str, 
    params: Optional[Dict[str, Any]] = None,
    session: Optional[aiohttp.ClientSession] = None
) -> Dict[str, Any]:
    """
    Helper function to make Twitter API requests with common error handling.
    
    Args:
        url: The API endpoint URL
        params: Query parameters for the request
        session: Optional existing aiohttp session to use
        
    Returns:
        The response data from the API
        
    Raises:
        Exception: If API request fails or returns an error
    """
    headers = {"X-API-Key": get_config("twitter_api_key")}
    
    # Use provided session or create a new one
    if session:
        async with session.get(url, headers=headers, params=params) as response:
            return await _handle_response(response)
    else:
        async with aiohttp.ClientSession() as new_session:
            async with new_session.get(url, headers=headers, params=params) as response:
                return await _handle_response(response)


async def _handle_response(response: aiohttp.ClientResponse) -> Dict[str, Any]:
    """
    Handle the HTTP response and extract data with error checking.
    
    Args:
        response: The aiohttp response object
        
    Returns:
        The response data from the API
        
    Raises:
        Exception: If response status is not 200 or API returns an error
    """
    if response.status != 200:
        error_text = await response.text()
        raise Exception(f"API request failed with status {response.status}: {error_text}")

    data = await response.json()

    if data.get("status") != "success":
        raise Exception(f"API returned error: {data.get('message', 'Unknown error')}")

    return data


async def get_user_tweets(
    user_id: Optional[str] = None,
    user_name: Optional[str] = None,
    limit: Optional[int] = None,
    until_date: Optional[datetime] = None,
    include_replies: bool = False,
) -> List[Dict[str, Any]]:
    """
    Retrieve tweets from a user with pagination support.

    Args:
        user_id: User ID of the user (recommended, more stable than userName)
        user_name: Screen name of the user (alternative to user_id)
        limit: Maximum number of tweets to retrieve
        until_date: Retrieve tweets until this date
        include_replies: Whether to include replies in the results

    Returns:
        List of tweet objects sorted by created_at

    Raises:
        ValueError: If neither user_id nor user_name is provided
        Exception: If API request fails
    """
    if not user_id and not user_name:
        raise ValueError("Either user_id or user_name must be provided")

    base_url = "https://api.twitterapi.io/twitter/user/last_tweets"

    all_tweets = []
    cursor = ""
    page_count = 0
    max_pages = 100  # Safety limit to prevent infinite loops

    async with aiohttp.ClientSession() as session:
        while page_count < max_pages:
            # Prepare request parameters
            params = {"cursor": cursor, "includeReplies": str(include_replies).lower()}

            # Add user identifier (userId takes precedence over userName)
            if user_id:
                params["userId"] = user_id
            else:
                params["userName"] = user_name

            try:
                data = await _make_twitter_api_request(base_url, params, session)

                # Handle nested data structure - tweets are inside data.tweets
                data_content = data.get("data", {})
                tweets = data_content.get("tweets", [])

                if not tweets:
                    logger.info("No more tweets found")
                    break

                # Add all tweets from this page
                all_tweets.extend(tweets)

                # Check if we should stop based on until_date
                if until_date:
                    # Check the oldest tweet in this page (last tweet since sorted by created_at desc)
                    oldest_tweet = tweets[-1]
                    created_at_str = oldest_tweet.get("createdAt", "")  # Use createdAt, not created_at
                    if created_at_str:
                        try:
                            # Parse format: "Sat Jun 07 05:42:18 +0000 2025"
                            oldest_tweet_date = datetime.strptime(created_at_str, "%a %b %d %H:%M:%S %z %Y")
                            if oldest_tweet_date < until_date:
                                logger.info(
                                    f"Reached until_date limit. Oldest tweet in page: {oldest_tweet_date}, until_date: {until_date}"
                                )
                                break
                        except ValueError as e:
                            logger.warning(f"Could not parse tweet createdAt: {created_at_str}, error: {e}")
                            # Continue processing if we can't parse the date
                    else:
                        logger.warning("Tweet has empty createdAt field, continuing processing")

                # Check if we've reached the limit
                if limit and len(all_tweets) >= limit:
                    all_tweets = all_tweets[:limit]
                    logger.info(f"Reached tweet limit of {limit}")
                    break

                # Check if there are more pages
                if not data.get("has_next_page", False):
                    logger.info("No more pages available")
                    break

                cursor = data.get("next_cursor", "")
                if not cursor:
                    logger.info("No next cursor available")
                    break

                page_count += 1
                logger.info(f"Retrieved page {page_count}, total tweets so far: {len(all_tweets)}")

                # Small delay to be respectful to the API
                await asyncio.sleep(0.1)

            except aiohttp.ClientError as e:
                raise Exception(f"Network error occurred: {str(e)}")
            except Exception as e:
                logger.error(f"Error retrieving tweets: {str(e)}")
                raise

    logger.info(f"Total tweets retrieved: {len(all_tweets)}")
    
    # Format all tweets using the format_tweet function
    formatted_tweets = []
    for tweet in all_tweets:
        try:
            formatted_tweet = format_tweet(tweet, user_id=user_id, username=user_name)
            formatted_tweets.append(formatted_tweet)
        except Exception as e:
            logger.warning(f"Failed to format tweet {tweet.get('id', 'unknown')}: {e}")
            # Include the original tweet if formatting fails
            formatted_tweets.append(tweet)
    
    return formatted_tweets


async def get_user_tweets_by_limit(
    user_id: Optional[str] = None, user_name: Optional[str] = None, limit: int = 100, include_replies: bool = False
) -> List[Dict[str, Any]]:
    """
    Convenience function to retrieve a specific number of tweets from a user.

    Args:
        user_id: User ID of the user
        user_name: Screen name of the user
        limit: Maximum number of tweets to retrieve
        include_replies: Whether to include replies in the results

    Returns:
        List of tweet objects sorted by created_at
    """
    return await get_user_tweets(user_id=user_id, user_name=user_name, limit=limit, include_replies=include_replies)


async def get_user_tweets_until_date(
    user_id: Optional[str] = None, user_name: Optional[str] = None, until_date: datetime = None, include_replies: bool = False
) -> List[Dict[str, Any]]:
    """
    Convenience function to retrieve tweets from a user until a specific date.

    Args:
        user_id: User ID of the user
        user_name: Screen name of the user
        until_date: Retrieve tweets until this date
        include_replies: Whether to include replies in the results

    Returns:
        List of tweet objects sorted by created_at
    """
    return await get_user_tweets(user_id=user_id, user_name=user_name, until_date=until_date, include_replies=include_replies)


async def get_user_tweets_since_date(
    user_id: Optional[str] = None, user_name: Optional[str] = None, since_date: datetime = None, include_replies: bool = False
) -> List[Dict[str, Any]]:
    """
    Convenience function to retrieve tweets from a user since a specific date.
    This function fetches all tweets from the API and filters them to only include
    tweets created after the specified date.

    Args:
        user_id: User ID of the user
        user_name: Screen name of the user
        since_date: Retrieve tweets created after this date
        include_replies: Whether to include replies in the results

    Returns:
        List of tweet objects created after since_date, sorted by created_at
    """
    assert since_date, "since_date must be provided"

    # Fetch all recent tweets (we'll filter them afterwards)
    # Note: Twitter API typically returns tweets in reverse chronological order
    all_tweets = await get_user_tweets(
        user_id=user_id, user_name=user_name, limit=None, include_replies=include_replies  # Get as many as possible
    )

    # Filter tweets to only include those created after since_date
    filtered_tweets = []
    for tweet in all_tweets:
        created_at_str = tweet.get("createdAt", "")
        if created_at_str:
            try:
                # Parse format: "Sat Jun 07 05:42:18 +0000 2025"
                tweet_date = datetime.strptime(created_at_str, "%a %b %d %H:%M:%S %z %Y")
                if tweet_date > since_date:
                    filtered_tweets.append(tweet)
                else:
                    # Since tweets are in reverse chronological order,
                    # once we hit a tweet older than since_date, we can stop
                    break
            except ValueError as e:
                logger.warning(f"Could not parse tweet createdAt: {created_at_str}, error: {e}")
                # Include the tweet if we can't parse the date to be safe
                filtered_tweets.append(tweet)

    logger.info(f"Filtered {len(filtered_tweets)} tweets since {since_date} from {len(all_tweets)} total tweets")
    
    # Format all filtered tweets using the format_tweet function
    formatted_tweets = []
    for tweet in filtered_tweets:
        try:
            formatted_tweet = format_tweet(tweet, user_id=user_id, username=user_name)
            formatted_tweets.append(formatted_tweet)
        except Exception as e:
            logger.warning(f"Failed to format tweet {tweet.get('id', 'unknown')}: {e}")
            # Include the original tweet if formatting fails
            formatted_tweets.append(tweet)
    
    return formatted_tweets


async def get_tweets_by_ids(tweet_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Retrieve tweets by their IDs.

    Args:
        tweet_ids: List of tweet IDs to retrieve

    Returns:
        List of tweet objects

    Raises:
        ValueError: If tweet_ids is empty
        Exception: If API request fails
    """
    if not tweet_ids:
        raise ValueError("tweet_ids must not be empty")

    base_url = "https://api.twitterapi.io/twitter/tweets"
    
    # Convert list to comma-separated string
    tweet_ids_str = ",".join(tweet_ids)
    params = {"tweet_ids": tweet_ids_str}

    try:
        data = await _make_twitter_api_request(base_url, params)

        # Handle nested data structure - tweets are inside data.tweets
        tweets = data.get("tweets", [])

        logger.info(f"Retrieved {len(tweets)} tweets by IDs")
        
        # Format all tweets using the format_tweet function
        formatted_tweets = []
        for tweet in tweets:
            try:
                formatted_tweet = format_tweet(tweet)
                formatted_tweets.append(formatted_tweet)
            except Exception as e:
                logger.warning(f"Failed to format tweet {tweet.get('id', 'unknown')}: {e}")
                # Include the original tweet if formatting fails
                formatted_tweets.append(tweet)
        
        return formatted_tweets

    except aiohttp.ClientError as e:
        raise Exception(f"Network error occurred: {str(e)}")
    except Exception as e:
        logger.error(f"Error retrieving tweets by IDs: {str(e)}")
        raise


async def get_user_info(user_name: str) -> Dict[str, Any]:
    """
    Retrieve user information by screen name.

    Args:
        user_name: The screen name of the user

    Returns:
        Dictionary containing user information

    Raises:
        ValueError: If user_name is not provided
        Exception: If API request fails
    """
    if not user_name:
        raise ValueError("user_name must be provided")

    base_url = "https://api.twitterapi.io/twitter/user/info"
    params = {"userName": user_name}

    try:
        data = await _make_twitter_api_request(base_url, params)

        # Return the user data
        user_data = data.get("data", {})
        logger.info(f"Retrieved user info for: {user_name}")
        
        # Import and apply profile formatting to match Connection1 format
        return format_profile(user_data)

    except aiohttp.ClientError as e:
        raise Exception(f"Network error occurred: {str(e)}")
    except Exception as e:
        logger.error(f"Error retrieving user info for {user_name}: {str(e)}")
        raise


async def get_user_followings(
    user_name: str,
    limit: Optional[int] = None,
    cursor: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve user followings with pagination support.
    Each page returns exactly 200 followings.

    Args:
        user_name: Screen name of the user
        limit: Maximum number of followings to retrieve (optional)
        cursor: Cursor for pagination (optional)

    Returns:
        Dictionary containing:
        - followings: List of following user objects
        - next_cursor: Cursor for next page (if available)
        - has_next_page: Boolean indicating if more pages are available

    Raises:
        ValueError: If user_name is not provided
        Exception: If API request fails
    """
    if not user_name:
        raise ValueError("user_name must be provided")

    base_url = "https://api.twitterapi.io/twitter/user/followings"
    
    all_followings = []
    current_cursor = cursor or ""
    page_count = 0
    max_pages = 100  # Safety limit to prevent infinite loops

    async with aiohttp.ClientSession() as session:
        while page_count < max_pages:
            # Prepare request parameters
            params = {"userName": user_name}
            if current_cursor:
                params["cursor"] = current_cursor

            try:
                data = await _make_twitter_api_request(base_url, params, session)

                # Handle nested data structure - followings are inside data
                data_content = data.get("data", {})
                followings = data_content.get("followings", [])

                if not followings:
                    logger.info("No more followings found")
                    break

                # Add all followings from this page
                all_followings.extend(followings)

                # Check if we've reached the limit
                if limit and len(all_followings) >= limit:
                    all_followings = all_followings[:limit]
                    logger.info(f"Reached followings limit of {limit}")
                    break

                # Check if there are more pages
                if not data.get("has_next_page", False):
                    logger.info("No more pages available")
                    break

                current_cursor = data.get("next_cursor", "")
                if not current_cursor:
                    logger.info("No next cursor available")
                    break

                page_count += 1
                logger.info(f"Retrieved page {page_count}, total followings so far: {len(all_followings)}")

                # Small delay to be respectful to the API
                await asyncio.sleep(0.1)

            except aiohttp.ClientError as e:
                raise Exception(f"Network error occurred: {str(e)}")
            except Exception as e:
                logger.error(f"Error retrieving followings for {user_name}: {str(e)}")
                raise

    logger.info(f"Total followings retrieved: {len(all_followings)}")
    
    return {
        "followings": all_followings,
        "next_cursor": current_cursor if page_count < max_pages else None,
        "has_next_page": bool(current_cursor) and page_count < max_pages,
        "total_count": len(all_followings)
    }


async def advanced_search(
    query: str,
    query_type: str = "Latest",
    limit: Optional[int] = None,
    cursor: Optional[str] = None
) -> Dict[str, Any]:
    """
    Advanced search for tweets with pagination support.
    Each page returns up to 20 tweets (sometimes less due to filtering).

    Args:
        query: The search query (e.g., "AI" OR "Twitter" from:elonmusk since:2021-12-31_23:59:59_UTC)
        query_type: The query type - either "Latest" or "Top" (default: "Latest")
        limit: Maximum number of tweets to retrieve (optional)
        cursor: Cursor for pagination (optional)

    Returns:
        Dictionary containing:
        - tweets: List of tweet objects
        - next_cursor: Cursor for next page (if available)
        - has_next_page: Boolean indicating if more pages are available
        - total_count: Total number of tweets retrieved

    Raises:
        ValueError: If query is not provided or query_type is invalid
        Exception: If API request fails
    """
    if not query:
        raise ValueError("query must be provided")
    
    if query_type not in ["Latest", "Top"]:
        raise ValueError("query_type must be either 'Latest' or 'Top'")

    base_url = "https://api.twitterapi.io/twitter/tweet/advanced_search"
    headers = {"X-API-Key": get_config("twitter_api_key")}
    
    all_tweets = []
    current_cursor = cursor or ""
    page_count = 0
    max_pages = 100  # Safety limit to prevent infinite loops

    async with aiohttp.ClientSession() as session:
        while page_count < max_pages:
            # Prepare request parameters
            params = {
                "query": query,
                "queryType": query_type
            }
            if current_cursor:
                params["cursor"] = current_cursor

            try:
                async with session.get(base_url, headers=headers, params=params) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"API request failed with status {response.status}: {error_text}")

                    data = await response.json()

                    # Advanced search returns tweets directly, no status field to check
                    tweets = data.get("tweets", [])

                    if not tweets:
                        logger.info("No more tweets found")
                        break

                    # Add all tweets from this page
                    all_tweets.extend(tweets)

                    # Check if we've reached the limit
                    if limit and len(all_tweets) >= limit:
                        all_tweets = all_tweets[:limit]
                        logger.info(f"Reached tweet limit of {limit}")
                        break

                    # Check if there are more pages
                    if not data.get("has_next_page", False):
                        logger.info("No more pages available")
                        break

                    current_cursor = data.get("next_cursor", "")
                    if not current_cursor:
                        logger.info("No next cursor available")
                        break

                    page_count += 1
                    logger.info(f"Retrieved page {page_count}, total tweets so far: {len(all_tweets)}")

                    # Small delay to be respectful to the API
                    await asyncio.sleep(0.1)

            except aiohttp.ClientError as e:
                raise Exception(f"Network error occurred: {str(e)}")
            except Exception as e:
                logger.error(f"Error performing advanced search: {str(e)}")
                raise

    logger.info(f"Total tweets retrieved from search: {len(all_tweets)}")
    
    # Format all tweets using the format_tweet function
    formatted_tweets = []
    for tweet in all_tweets:
        try:
            formatted_tweet = format_tweet(tweet)
            formatted_tweets.append(formatted_tweet)
        except Exception as e:
            logger.warning(f"Failed to format tweet {tweet.get('id', 'unknown')}: {e}")
            # Include the original tweet if formatting fails
            formatted_tweets.append(tweet)
    
    return {
        "tweets": formatted_tweets,
        "next_cursor": current_cursor if page_count < max_pages else None,
        "has_next_page": bool(current_cursor) and page_count < max_pages,
        "total_count": len(formatted_tweets)
    }


