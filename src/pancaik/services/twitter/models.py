"""
Twitter data models and formatting utilities.

This module provides common data structure definitions and formatting
functions for working with Twitter data.
"""

from datetime import datetime, timezone
from typing import Dict, Optional, List


# Global field mappings to standardize data across different Twitter API sources
PROFILE_FIELD_MAPPINGS = {
    # TwitterAPI key -> Standard key (based on official Twitter API v2)
    "userName": "username",
    "screenName": "name",  # TwitterAPI uses screenName, official API uses name
    "screen_name": "username",  # v1.1 API compatibility
    "description": "bio", 
    "isVerified": "verified",
    "createdAt": "created_at",
    "followers_count": "followersCount",
    "following_count": "followingCount", 
    "friends_count": "followingCount",  # v1.1 API uses friends_count for following
    "favourites_count": "favoritesCount",
    "statuses_count": "statusesCount",
    "media_tweets_count": "mediaTweetsCount",
    "profile_image_url_https": "profileImageUrl",
    "profile_banner_url": "profileBannerUrl",
    "can_dm": "canDm",
    # Keep fields that are already standardized
    "id": "id",
    "name": "name", 
    "username": "username",
    "location": "location",
    "url": "url",
    "email": "email",
    "protected": "protected",
    "verified": "verified",
    "created_at": "created_at",
}

TWEET_FIELD_MAPPINGS = {
    # TwitterAPI key -> Standard key (minimal mapping for compatibility)
    "author_id": "author_id",
    "edit_history_tweet_ids": "edit_history_tweet_ids",
}

MENTION_FIELD_MAPPINGS = {
    # TwitterAPI key -> Standard key
    "id_str": "id",
    "screen_name": "username",
}


def normalize_mentions(mentions: List[Dict]) -> List[Dict]:
    """Normalize mentions to consistent format used by Connection API."""
    if not mentions:
        return []
    
    normalized = []
    for mention in mentions:
        # Convert TwitterAPI format to Connection format using global mappings
        normalized_mention = {}
        
        # Apply global mention field mappings
        for key, value in mention.items():
            if key == 'indices':
                continue  # Skip 'indices' field as Connection format doesn't include it
            
            # Use global mention mapping if available, otherwise use original key
            mapped_key = MENTION_FIELD_MAPPINGS.get(key, key)
            
            # Special handling for id field to ensure it's a string
            if mapped_key == 'id':
                normalized_mention[mapped_key] = str(value)
            else:
                normalized_mention[mapped_key] = value
        
        normalized.append(normalized_mention)
    
    return normalized


def format_tweet(tweet: Dict, user_id: Optional[str] = None, username: Optional[str] = None) -> Dict:
    """Format raw tweet data into a consistent structure."""
    assert tweet is not None, "Tweet must not be None"
    assert "id" in tweet, "Tweet must have an ID"
    assert "text" in tweet, "Tweet must have text content"

    # Handle created_at from multiple possible sources
    created_at = tweet.get("created_at") or tweet.get("timeParsed") or tweet.get("createdAt")
    if isinstance(created_at, str):
        # Handle different date formats
        if created_at.endswith("Z"):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        elif "+0000" in created_at:
            # Handle format like "Fri Jun 13 11:57:14 +0000 2025"
            try:
                created_at = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
            except ValueError:
                # Fallback to ISO format
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        else:
            created_at = datetime.fromisoformat(created_at)

    if created_at:
        created_at = created_at.replace(tzinfo=timezone.utc)

    # Safely handle entities and mentions
    entities = tweet.get("entities") or {}
    mentions = entities.get("mentions", []) or entities.get("user_mentions", [])
    if not mentions and tweet.get("mentions"):
        mentions = tweet["mentions"]

    # Normalize mentions to Connection format
    normalized_mentions = normalize_mentions(mentions)

    # Handle conversation ID from multiple sources
    conv_id = (tweet.get("conversation_id") or 
               tweet.get("conversationId") or 
               tweet.get("inReplyToId") if tweet.get("isReply") else tweet.get("id"))

    # Handle replied_to_id from multiple sources
    replied_id = None
    if tweet.get("referenced_tweets"):
        for ref in tweet["referenced_tweets"]:
            if ref.get("type") == "replied_to":
                replied_id = ref.get("id")
                break

    if not replied_id:
        replied_id = (tweet.get("inReplyToStatusId") or 
                     tweet.get("inReplyToId") if tweet.get("isReply") else None)

    # Handle username from multiple sources
    final_username = (username or 
                     tweet.get("username") or 
                     (tweet.get("author", {}).get("userName") if tweet.get("author") else None))

    # Handle user_id from multiple sources
    final_user_id = (str(user_id) if user_id else 
                    str(tweet.get("user_id")) if tweet.get("user_id") else
                    str(tweet.get("author", {}).get("id")) if tweet.get("author", {}).get("id") else None)

    # Start with the core mapped fields
    result = {
        "_id": str(tweet["id"]),
        "conversation_id": str(conv_id) if conv_id is not None else None,
        "replied_to_id": str(replied_id) if replied_id is not None else None,
        "mentions": normalized_mentions,
        "user_id": final_user_id,
        "username": final_username,
        "text": tweet["text"],
        "created_at": created_at,
    }

    # Use global tweet field mappings for consistency
    key_mapping = TWEET_FIELD_MAPPINGS

    # Add all remaining keys from the original tweet, applying minimal mappings
    mapped_keys = {"id", "text", "created_at", "timeParsed", "createdAt", "entities", 
                   "mentions", "conversation_id", "conversationId", "referenced_tweets", 
                   "inReplyToStatusId", "inReplyToId", "username", "user_id", "author"}
    
    for key, value in tweet.items():
        if key not in mapped_keys:
            # Use mapped key if available, otherwise use original key
            mapped_key = key_mapping.get(key, key)
            result[mapped_key] = value

    return result


def format_profile(profile: Dict) -> Dict:
    """Format raw profile data into consistent structure."""
    if not profile:
        return profile
    
    # Create new profile with mapped keys using global mappings
    result = {}
    
    for key, value in profile.items():
        # Use global profile mapping if available, otherwise use original key
        mapped_key = PROFILE_FIELD_MAPPINGS.get(key, key)
        result[mapped_key] = value
    
    return result


def format_following(following: Dict) -> Dict:
    """Format raw following user data into consistent structure."""
    if not following:
        return following
    
    # Create new following with mapped keys using global profile mappings
    # Following users have the same structure as profiles
    result = {}
    
    for key, value in following.items():
        # Use global profile mapping if available, otherwise use original key
        mapped_key = PROFILE_FIELD_MAPPINGS.get(key, key)
        result[mapped_key] = value
    
    return result
