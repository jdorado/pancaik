"""
Twitter indexing tools for agents.

This module provides tools for indexing tweets from users and mentions.
"""

import re
from datetime import datetime
from typing import Any, Dict, Tuple

from ...core.ai_logger import ai_logger
from ...core.config import get_config, logger
from ...core.connections import ConnectionHandler
from ...tools.base import tool
from ...utils.ai_router import get_completion
from ...utils.json_parser import extract_json_content
from ...utils.prompt_utils import get_prompt
from . import client as twitter_client
from .client import TwitterClient
from .handlers import TwitterHandler


async def get_conversation(post: Dict, client: TwitterClient, handler: TwitterHandler, depth: int = 10) -> Tuple[str, int, int]:
    """
    Retrieves the conversation thread for a given post.

    Args:
        post: The tweet/post to retrieve conversation for
        credentials: Twitter API credentials
        handler: TwitterHandler instance for database operations
        depth: Maximum depth of conversation thread to retrieve

    Returns:
        Tuple of (conversation_text, reply_count, handle_count)
    """
    # Preconditions
    assert post, "Post must be provided"
    assert handler, "TwitterHandler must be provided"
    assert isinstance(handler, TwitterHandler), "handler must be a TwitterHandler instance"

    agent_user = client.get_username()
    assert agent_user, "Username must be in credentials"

    def remove_mentions(text):
        return re.sub(r"@\w+", "", text).strip()

    def count_handles(text):
        return len(re.findall(r"@\w+", text))

    visited_level = 0
    posts = {}
    posts[post["_id"]] = post
    current_post = post

    # Get collection for database operations
    collection = handler.get_collection()

    # Get all parent posts in the conversation
    while visited_level < depth and current_post.get("replied_to_id"):
        post_id = str(current_post.get("replied_to_id"))
        # top of conversation
        if not post_id:
            break

        # Use the handler's collection to find the parent post
        parent_post = await collection.find_one({"_id": str(post_id)})

        if not parent_post:
            # Fetch from Twitter API if not in database
            parent_post = await client.get_tweet(post_id)
            if parent_post:
                # Use the handler to insert the new tweet
                await handler.insert_tweets([parent_post])

        if not parent_post:
            # Fail task as we can't reconstruct the conversation
            raise Exception(f"Failed to retrieve tweet {post_id}. Cannot reconstruct conversation.")

        posts[parent_post["_id"]] = parent_post
        current_post = parent_post
        visited_level += 1

    # Reconstruct conversation in chronological order
    conversation_array = []
    current_post = post

    # Find the oldest parent post
    while current_post.get("replied_to_id"):
        post_id = str(current_post.get("replied_to_id"))
        if post_id not in posts:
            break
        current_post = posts[post_id]

        text = remove_mentions(current_post.get("text", ""))
        username = current_post.get("username") or current_post.get("user_id") or "Other User"
        conversation_array.insert(0, f"<post>{username}: {text}</post>")

    # Join the conversation messages
    history = "\n".join(conversation_array)

    # Count replies from agent user
    count_replies = sum(1 for msg in conversation_array[1:] if agent_user in msg)

    # Add the current post text
    text = remove_mentions(post.get("text", ""))
    username = post.get("username") or post.get("user_id") or "Other User"

    # Format the complete conversation context
    conversation = f"""
    <post_type>
    This is a conversation on twitter.
    </post_type>

    <thread>
    {history}
    </thread>

    <reply_to>
    <post>{username}: {text}</post>
    </reply_to>

    <your_username>
    {agent_user}
    </your_username>
    """

    # Return the conversation text, reply count, and handle count
    return conversation, count_replies, count_handles(post["text"])


@tool(agents=["agent_twitter_index_mentions"])
async def twitter_select_mentions(
    data_store: Dict[str, Any],
    twitter_connection: str,
    target_handle: str,
    max_thread_replies: int = 3,
    max_mentioned_users: int = 2,
    reply_evaluation_rules=None,
):
    """
    Selects an unresponded mention to reply to from the Twitter database.

    Args:
        data_store: Agent's data store containing configuration and state

    Returns:
        Dictionary with selected mention context or False if no suitable mentions found
    """
    # Preconditions
    assert data_store, "Data store must be provided"
    config = data_store.get("config", {})

    # Extract agent context for AI logging
    agent_id = data_store.get("agent_id")
    owner_id = config.get("owner_id")
    agent_name = config.get("name")

    ai_logger.thinking(f"Selecting an unresponded mention to reply to for @{target_handle}...", agent_id, owner_id, agent_name)

    # Get database instance from config
    db = get_config("db")
    if db is None:
        raise ValueError("Database not initialized in config")

    # Initialize connection handler with db
    connection_handler = ConnectionHandler(db)
    twitter = await twitter_client.get_client(twitter_connection, connection_handler)

    # Create query to search for mentions excluding retweets
    username = target_handle.replace("@", "").strip()
    assert username, "Twitter username must be in the credentials"

    # reply from account handle
    reply_account = twitter.get_username()

    # Ensure we have a handler for database operations
    handler = TwitterHandler()
    collection = handler.get_collection()

    # Select all mentions not yet replied to
    query = {
        "$and": [
            {"mentions.username": username},
            {"replied_by": {"$nin": [reply_account]}},
            {"username": {"$ne": username}},
        ]
    }

    ai_logger.action(f"Querying for mentions not yet replied to for @{username}...", agent_id, owner_id, agent_name)

    # Search for mentions
    mentions = await collection.find(query).sort([("created_at", -1)]).to_list(length=1000)

    # Remove RT
    mentions = [mention for mention in mentions if not mention.get("text", "").startswith("RT @" + username)]

    # Create the default return for no mentions case
    status = "no_mentions_found" if not mentions else "no_suitable_mentions"

    # Iterate through mentions until we find a suitable one
    for mention in mentions:
        try:
            ai_logger.action(f"Evaluating mention {mention.get('_id')} for reply suitability...", agent_id, owner_id, agent_name)
            # Get full conversation
            conversation, count_replies, handle_count = await get_conversation(mention, twitter, handler)
        except Exception as e:
            logger.warning(f"Error in get_conversation for mention {mention.get('_id')}: {e}", exc_info=True)
            return {
                "status": "error",
                "should_exit": True,
                "error": str(e),
                "mention_id": mention.get("_id"),
            }

        # Determine if we should reply
        should_reply = handle_count <= int(max_mentioned_users) and count_replies < int(max_thread_replies)

        # if reply_evaluation_rules is not None, evaluate the conversation
        output_format = f"""
        OUTPUT IN JSON: Strict JSON format, no additional text.
        "should_reply": true or false
        """
        if reply_evaluation_rules:
            prompt_data = {
                "task": "Decide if the conversation is worth replying to, extrictly follow the guidelines.",
                "today": datetime.utcnow().strftime("%Y-%m-%d"),
                "context": data_store.get("context", {}),
                "guidelines": reply_evaluation_rules,
                "conversation": conversation,
                "output_format": output_format,
            }

            prompt = get_prompt(prompt_data)
            model_id = config.get("ai_models", {}).get("research-mini")
            response = await get_completion(prompt=prompt, model_id=model_id)
            parsed_response = extract_json_content(response) or {}
            should_reply = should_reply and parsed_response.get("should_reply", should_reply)

        if should_reply:
            logger.info(f"Selected mention {mention['_id']} to reply to")
            ai_logger.result(f"Selected mention {mention['_id']} to reply to.", agent_id, owner_id, agent_name)
            return {
                "status": "success",
                "values": {"context": {"conversation": conversation}, "reply_to_id": mention["_id"]},
            }
        else:
            # Mark as reviewed only if not suitable
            await collection.update_one({"_id": mention["_id"]}, {"$push": {"replied_by": reply_account}})
            logger.info(
                f"Mention {mention['_id']} not suitable for reply (handle_count={handle_count}, count_replies={count_replies}). Marked as reviewed and continuing to next mention."
            )
            ai_logger.action(
                f"Mention {mention['_id']} not suitable for reply (handle_count={handle_count}, count_replies={count_replies}). Marked as reviewed.",
                agent_id,
                owner_id,
                agent_name,
            )

    # If we've gone through all mentions and none are suitable
    logger.info(f"No {'unreplied' if not mentions else 'suitable'} mentions found")
    ai_logger.result(f"No {'unreplied' if not mentions else 'suitable'} mentions found for @{username}.", agent_id, owner_id, agent_name)
    return {"status": status, "values": {}, "should_exit": True}
