"""
Twitter data models and formatting utilities.

This module provides common data structure definitions and formatting
functions for working with Twitter data.
"""

from datetime import datetime, timezone
from typing import Dict, Optional


def format_tweet(tweet: Dict, user_id: Optional[str] = None, username: Optional[str] = None) -> Dict:
    """Format raw tweet data into a consistent structure."""
    assert tweet is not None, "Tweet must not be None"
    assert "id" in tweet, "Tweet must have an ID"
    assert "text" in tweet, "Tweet must have text content"

    created_at = tweet.get("created_at") or tweet.get("timeParsed")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

    if created_at:
        created_at = created_at.replace(tzinfo=timezone.utc)

    # Safely handle entities and mentions
    entities = tweet.get("entities") or {}
    mentions = entities.get("mentions", [])
    if not mentions and tweet.get("mentions"):
        mentions = tweet["mentions"]

    conv_id = tweet.get("conversation_id") or tweet.get("conversationId")

    # Handle referenced tweets for replies
    replied_id = None
    if tweet.get("referenced_tweets"):
        for ref in tweet["referenced_tweets"]:
            if ref.get("type") == "replied_to":
                replied_id = ref.get("id")
                break

    if not replied_id:
        replied_id = tweet.get("inReplyToStatusId")

    return {
        "_id": str(tweet["id"]),
        "conversation_id": str(conv_id) if conv_id is not None else None,
        "replied_to_id": str(replied_id) if replied_id is not None else None,
        "mentions": mentions,
        "user_id": str(user_id) if user_id else None,
        "username": username or tweet.get("username"),
        "text": tweet["text"],
        "created_at": created_at,
    }
