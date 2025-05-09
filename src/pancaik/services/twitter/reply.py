"""
Twitter reply tools for agents.

This module provides tools for composing and sending replies to tweets.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from ...core.config import get_config, logger
from ...core.connections import ConnectionHandler
from ...tools.base import tool
from ...utils.ai_router import get_completion
from ...utils.json_parser import extract_json_content
from ...utils.prompt_utils import get_prompt
from . import client, indexing
from .client import TwitterClient
from .handlers import TwitterHandler


@tool()
async def twitter_reply(
    twitter_connection: str, reply_to_id: str, reply_guidelines: str, data_store: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Composes and sends a reply to a tweet using provided guidelines.

    Args:
        twitter_connection: Connection ID for Twitter credentials
        reply_to_id: ID of the tweet to reply to
        reply_guidelines: Guidelines for composing the reply
        data_store: Optional data store for additional context

    Returns:
        Dictionary with reply operation results
    """
    # Preconditions
    assert reply_to_id, "Reply tweet ID must be provided"
    assert reply_guidelines, "Reply guidelines must be provided"

    # Get database instance from config
    db = get_config("db")
    if db is None:
        raise ValueError("Database not initialized in config")

    # Initialize connection handler with db
    connection_handler = ConnectionHandler(db)
    twitter: TwitterClient = await client.get_client(twitter_connection, connection_handler)

    # Get the semaphore for Twitter API rate limiting
    semaphore = get_config("twitter_semaphore")
    assert semaphore is not None, "Twitter semaphore must be available in config"

    # Initialize handler for database operations
    handler = TwitterHandler()

    # 1. Compose the reply using guidelines
    reply_requirements = f"""
    Maximum length: 280 characters
    No markdown formatting
    No @mentions including your own username
    """
    output_format = f"""
    OUTPUT IN JSON: Strict JSON format, no additional text.
    "tweet": "Your tweet here"
    """
    prompt_data = {
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "task": "Compose a twitter reply following the reply guidelines and within context.",
        "reply_requirements": reply_requirements,
        "reply_guidelines": reply_guidelines,
        "context": data_store.get("context", {}),
        "output_format": output_format,
    }
    prompt = get_prompt(prompt_data, "reply_request")
    model_id = data_store.get("config", {}).get("ai_models", {}).get("composing")
    response = await get_completion(prompt=prompt, model_id=model_id)
    parsed_response = extract_json_content(response) or {}

    if not parsed_response or "tweet" not in parsed_response:
        logger.error(f"Failed to compose reply for tweet {reply_to_id}")
        semaphore.release()
        return {"status": "error", "message": "Failed to compose reply", "reply_to_id": reply_to_id}

    # 2. Send the reply
    # Acquire semaphore to respect rate limits
    await semaphore.acquire()
    reply_tweet = await twitter.create_tweet(text=parsed_response["tweet"], reply_id=reply_to_id)
    # Release the semaphore
    semaphore.release()

    if not reply_tweet or "id" not in reply_tweet:
        logger.error(f"Failed to send reply to tweet {reply_to_id}")
        semaphore.release()
        return {"status": "error", "message": "Failed to send reply", "reply_to_id": reply_to_id}

    # 3. Mark the original tweet as replied
    username = twitter.get_username()
    collection = handler.get_collection()
    result = await collection.update_one({"_id": reply_to_id}, {"$push": {"replied_by": username}})

    # 4. Index the reply tweet
    index_result = await indexing.index_tweet_by_id(twitter_connection=twitter_connection, tweet_id=reply_tweet["id"])

    # Postcondition - ensure we have the reply results
    result = {
        "status": "success",
        "values": {
            "context": {
                "tweet": parsed_response["tweet"],
            },
            "outputs": {
                "tweet": parsed_response["tweet"],
                "tweet_url": f"https://x.com/{username}/status/{reply_tweet['id']}",
            },
        },
    }

    logger.info(f"Successfully replied to tweet {reply_to_id}")
    return result
