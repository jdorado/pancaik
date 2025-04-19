"""
Twitter search query generation tools.

This module provides tools for generating search queries based on research.
"""

from datetime import datetime
from typing import Any, Dict

from ....core.config import logger
from ....core.data_handler import DataHandler
from ....services.twitter.tools.search import search_tweets
from ....tools.base import tool
from ....utils.ai_router import get_completion
from ....utils.json_parser import extract_json_content


@tool
async def generate_daily_search_queries_from_research(data_store: Dict[str, Any]):
    """
    Generates daily search queries based on research findings.

    Takes the output from daily research and extracts key search terms for Twitter,
    identifying relevant keywords, hashtags, and accounts to search for engagement.

    Args:
        data_store: Agent's data store containing configuration, state, and context

    Returns:
        Dictionary with operation status and values to be shared in data_store
    """
    assert data_store, "Data store must be provided"

    # Get necessary configuration
    config = data_store.get("config", {})

    # Get agent_id, required for per-agent storage
    agent_id = data_store.get("agent_id")
    assert agent_id, "agent_id must be configured"

    # Get agent profile/bio
    agent_bio = config.get("bio", "")
    guidelines = config.get("guidelines", "")

    # Get research results from data_store
    research_results = data_store.get("daily_research_results", {})
    assert research_results, "daily_research_results must be available in data_store"

    # Get optional daily content if available
    daily_content = data_store.get("daily_content", {})

    # Get query generation model
    query_model_id = config.get("ai_models", {}).get("analyzing")

    # Initialize database handler
    handler = DataHandler(collection_name="search_queries_cache")

    now = datetime.utcnow()
    today_date = now.strftime("%Y-%m-%d")

    # Check if we already have generated search queries for today
    cache_key = f"search_queries_{agent_id}_{today_date}"
    cached_queries = await handler.get_data_by_key(cache_key)

    if cached_queries:
        logger.info(f"Using cached search queries for agent {agent_id} dated {today_date}")
        return {
            "status": "success",
            "message": "Retrieved cached daily search queries",
            "values": {"daily_search_queries": cached_queries.get("content", {})},
        }

    # Create prompt with XML structure
    prompt = f"""
    <profile>
        TODAY: {today_date}
        ABOUT: {agent_bio}
    </profile>
    
    <task>
        Extract the most relevant search queries for Twitter based on the provided research data. 
        Focus on terms that will help find tweets the agent should engage with based on its mission and profile.
    </task>
    
    <guidelines>
    {guidelines}
    </guidelines>
    
    <context>
        Research data collected on {today_date}.
        {research_results}
        {f"Additional daily content: {daily_content}" if daily_content else ""}
    </context>
    
    <instructions>
        1. Analyze the research data to identify 80-100 key search queries based on relevant keywords, hashtags, and accounts.
        2. For each query, create a concise 'query_string' that will be used for Twitter search (e.g., hashtags, keywords, account names).
        3. Keep query strings very short, preferably 1-3 terms on average.
        4. Return the results in the specified structured JSON format.
    </instructions>
    
    <output_format>
    JSON output a list of, use standard json without any escaped or quoted text
        query_string: "The actual search query text",
        relevance_score: 0-100
    </output_format>
    """

    try:
        # Get completion and extract JSON content
        response = await get_completion(prompt=prompt, model_id=query_model_id)
        generated_queries = extract_json_content(response) or {}

        # If the dictionary has only one key, extract the first value
        if generated_queries and len(generated_queries.keys()) == 1:
            generated_queries = generated_queries[list(generated_queries.keys())[0]]

        # Save the generated queries to the database
        if await handler.save_data(cache_key, generated_queries, now):
            logger.info(f"Successfully generated and saved search queries for agent {agent_id}")
            return {
                "status": "success",
                "message": "Daily search queries generated and saved successfully",
                "values": {"daily_search_queries": generated_queries},
            }
        else:
            logger.error(f"Failed to save search queries for agent {agent_id}")
            return {
                "status": "error",
                "message": "Failed to save generated search queries",
                "values": {"daily_search_queries": generated_queries},
            }
    except Exception as e:
        logger.error(f"Error during search query generation: {e}")
        return {"status": "error", "message": f"Search query generation failed: {str(e)}", "values": {}}


@tool
async def search_posts_to_reply(data_store: Dict[str, Any]):
    """
    Selects the most relevant, unused search queries from the daily generated queries.
    Searches for suitable posts to reply to, respecting interaction time limits.

    Retrieves daily search queries, filters out those already marked as used, ranks
    the remaining by relevance score, and selects a batch of high-relevance queries.

    Args:
        data_store: Agent's data store containing daily_search_queries.

    Returns:
        Dictionary with operation status and the selected search queries added to values.
    """
    assert data_store, "Data store must be provided"

    daily_search_queries = data_store.get("daily_search_queries")
    assert daily_search_queries is not None, "daily_search_queries must be available in data_store"
    assert isinstance(daily_search_queries, list), "daily_search_queries must be a list"

    agent_id = data_store.get("agent_id")
    assert agent_id, "agent_id must be configured"

    logger.debug(f"Selecting search queries for agent {agent_id} from {len(daily_search_queries)} available queries.")

    # Get config
    config = data_store.get("config", {})

    # Get twitter credentials
    credentials = config.get("twitter", {}).get("credentials", {})
    assert credentials, "Twitter credentials must be in the agent's data store"

    # Get agent username
    username = credentials.get("username")
    assert username, "Twitter username must be in the credentials"

    # Get Twitter configuration for time limits
    twitter_config = config.get("twitter", {})
    reply_time_limit = twitter_config.get("default_replies_min_hours_between", 72)  # Default to 72 hours between replies

    # Set date constraints for search - limit to last 24 hours
    from datetime import timedelta

    from_date = datetime.utcnow() - timedelta(hours=24)
    date_str = from_date.strftime("%Y-%m-%d")

    # Sort queries by last_used_date (None first) and then by relevance_score
    now = datetime.utcnow()

    # Sort first by last_used_date (None first) and then by relevance_score
    try:
        sorted_queries = sorted(
            daily_search_queries,
            key=lambda x: (x.get("last_used_date") is not None, x.get("last_used_date", now), -x.get("relevance_score", 0)),
        )

        # Create a handler for the twitter collection
        handler = DataHandler(collection_name="twitter")
        collection = handler.get_collection()

        # Get recent interactions to respect time limits
        # Use aggregation to get the most recent reply interactions
        pipeline = [
            {"$match": {"interactions_by": username, "interaction_type": "replies"}},  # Only looking at replies type interactions
            {
                "$group": {
                    "_id": "$username",  # Group by the username we replied to
                    "last_interaction": {"$max": "$created_at"},  # Get the most recent interaction
                }
            },
        ]

        # Execute the aggregation
        recent_interactions_cursor = collection.aggregate(pipeline)
        recent_interactions = await recent_interactions_cursor.to_list(length=None)

        # Create a dictionary of usernames and their last interaction times
        ineligible_users = set()
        for interaction in recent_interactions:
            username_replied_to = interaction["_id"]
            last_time = interaction["last_interaction"]
            hours_since = (now - last_time).total_seconds() / 3600

            # If we've replied to this user recently, add to ineligible list
            if hours_since < reply_time_limit:
                ineligible_users.add(username_replied_to)
                logger.debug(f"User {username_replied_to} is ineligible for replies (last replied {hours_since:.1f} hours ago)")

        # Sequentially try search queries until we find a suitable post to reply to
        post = None
        used_query = None

        for query in sorted_queries:
            base_query = query.get("query_string", "")
            if not base_query:
                continue

            # Enhance the query with date constraints and filtering parameters
            enhanced_query = f"{base_query} min_faves:20 -filter:links -filter:replies since:{date_str}"

            logger.info(f"Searching Twitter for query: {base_query}")

            # Search twitter for the query
            search_result = await search_tweets(enhanced_query, data_store)

            if search_result.get("status") != "success" or not search_result.get("results"):
                logger.info(f"No results found for query: {base_query}")
                continue

            # Get search results
            search_results = search_result.get("results", [])

            # Remove self posts and retweets
            search_results = [
                result
                for result in search_results
                if not result.get("text", "").startswith("RT @" + username) and result.get("username") != username
            ]

            if not search_results:
                logger.info(f"No valid results after filtering for query: {base_query}")
                continue

            # Get post IDs
            ids = [result["id"] for result in search_results]

            # Select all posts not yet replied to
            existing = await collection.find({"_id": {"$in": ids}}).to_list(length=100)

            # Get IDs of already interacted posts (where we've already replied)
            replied_ids = [
                doc["_id"] for doc in existing if username in doc.get("interactions_by", []) and doc.get("interaction_type") == "replies"
            ]

            # Filter out posts that have already been replied to or from ineligible users
            search_results = [
                result for result in search_results if result["id"] not in replied_ids and result.get("username") not in ineligible_users
            ]

            if not search_results:
                logger.info(f"No eligible posts to reply to for query: {base_query}")
                continue

            # Select the first post to reply to
            post = search_results[0]
            used_query = query
            logger.info(f"Found post to reply to: {post.get('id')} - {post.get('text')[:50]}...")
            break

        if not post:
            logger.info(f"No posts found to reply to after trying {len(sorted_queries)} queries")
            return {"status": "no_results", "message": "No posts found to reply to", "values": {}}

        # Mark the post as being replied to
        post_id = post["id"]

        # If post is not yet in the database, save it
        existing_post_ids = [doc["_id"] for doc in existing]
        if post_id not in existing_post_ids:
            # Prepare document for saving
            doc = {
                "_id": post_id,
                "text": post.get("text", ""),
                "username": post.get("username", ""),
                "created_at": post.get("created_at"),
                "interactions_by": [username],
                "interaction_type": "replies",
            }
            await collection.insert_one(doc)
            logger.info(f"Saved new post {post_id} to database")
        else:
            # Update existing document to mark as replied to
            await collection.update_one(
                {"_id": post_id}, {"$push": {"interactions_by": username}, "$set": {"interaction_type": "replies", "created_at": now}}
            )
            logger.info(f"Updated post {post_id} to mark as replied to by {username}")

        # Update the query with last used date
        handler = DataHandler(collection_name="search_queries_cache")
        today_date = now.strftime("%Y-%m-%d")
        cache_key = f"search_queries_{agent_id}_{today_date}"

        cached_data = await handler.get_data_by_key(cache_key)
        if cached_data and "content" in cached_data and isinstance(cached_data["content"], list):
            cached_queries = cached_data["content"]
            updated = False

            for i, q in enumerate(cached_queries):
                if isinstance(q, dict) and q.get("query_string") == used_query.get("query_string"):
                    cached_queries[i]["last_used_date"] = now
                    updated = True
                    logger.info(f"Updated last_used_date for query '{used_query.get('query_string')}'")
                    break

            if updated:
                await handler.save_data(cache_key, cached_queries, now)

        # Prepare the conversation context for reply generation
        conversation = f"""
        <post_type>
        You are about to reply to a post. 
        Make sure you understand the context of the conversation before proceeding.
        Make sure you reply to the post by user.
        Reply must be 180 chars or less
        </post_type>

        <reply_to>
        {post.get('username', '')}: {post.get('text', '')}
        </reply_to>
        """

        # Prepare data to return
        return {
            "status": "success",
            "message": "Found post to reply to",
            "values": {
                "context": conversation,
                "reply_to_id": post_id,
                "selected_search_query": used_query,
                "interaction_type": "reply",  # Add interaction type for tracking
            },
        }
    except TypeError as e:
        logger.error(f"Error sorting search queries for agent {agent_id}: {e}. Queries: {daily_search_queries}")
        return {"status": "error", "message": f"Error sorting search queries: {e}", "values": {}}
