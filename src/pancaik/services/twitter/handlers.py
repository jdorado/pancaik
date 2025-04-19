"""
Twitter database handlers for persisting Twitter data.

This module provides classes for interacting with the database for Twitter-related operations,
centralizing all database access in one place.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from ...core.config import get_config, logger


class TwitterHandler:
    """Handler for Twitter-related database operations."""

    def __init__(self):
        """Initialize the Twitter handler."""
        self.db = get_config("db")
        assert self.db is not None, "Database must be initialized"

    def get_collection(self):
        """Get the Twitter collection from the database."""
        return self.db.twitter

    def get_users_collection(self):
        """Get the Twitter users collection from the database."""
        return self.db.twitter_users

    async def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Get a user from the database by username."""
        assert username, "Username must not be empty"
        collection = self.get_users_collection()
        return await collection.find_one({"_id": username})

    async def update_user(self, user: Dict[str, Any]) -> bool:
        """Update a user in the database."""
        assert user, "User must not be empty"
        assert "_id" in user, "User must have an _id field"

        collection = self.get_users_collection()
        result = await collection.replace_one({"_id": user["_id"]}, user, upsert=True)
        return result.acknowledged

    async def get_existing_tweet_ids(self, tweet_ids: List[str]) -> List[str]:
        """Get a list of tweet IDs that already exist in the database."""
        assert tweet_ids, "Tweet IDs must not be empty"

        collection = self.get_collection()
        cursor = collection.find({"_id": {"$in": tweet_ids}}, projection=["_id"])
        existing = await cursor.to_list(length=len(tweet_ids))
        return [doc["_id"] for doc in existing]

    async def insert_tweets(self, tweets: List[Dict[str, Any]]) -> bool:
        """Insert multiple tweets into the database."""
        assert tweets, "Tweets must not be empty"

        collection = self.get_collection()
        try:
            result = await collection.insert_many(tweets)
            logger.info(f"Inserted {len(result.inserted_ids)} tweets")
            return True
        except Exception as e:
            logger.error(f"Error inserting tweets: {e}")
            return False

    async def get_tweet(self, tweet_id: str) -> Optional[Dict[str, Any]]:
        """Get a tweet from the database by ID."""
        assert tweet_id, "Tweet ID must not be empty"

        collection = self.get_collection()
        return await collection.find_one({"_id": tweet_id})

    async def search_tweets(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Search for tweets in the database."""
        assert query, "Query must not be empty"
        assert limit > 0, "Limit must be positive"

        collection = self.get_collection()
        cursor = collection.find({"$text": {"$search": query}}, sort=[("created_at", -1)], limit=limit)
        return await cursor.to_list(length=limit)

    async def get_tweets_by_user(self, username: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get tweets by a specific user."""
        assert username, "Username must not be empty"
        assert limit > 0, "Limit must be positive"

        collection = self.get_collection()
        cursor = collection.find({"username": username}, sort=[("created_at", -1)], limit=limit)
        return await cursor.to_list(length=limit)

    async def get_tweets_from_users(
        self, usernames: List[str], min_date: Optional[datetime] = None, limit: int = 30
    ) -> List[Dict[str, Any]]:
        """Get tweets from multiple users with date filtering in a single database query.

        Args:
            usernames: List of usernames to fetch tweets from
            min_date: Optional minimum date for tweets
            limit: Maximum number of tweets to return

        Returns:
            List of tweet documents sorted by created_at descending
        """
        assert usernames, "Usernames list must not be empty"
        assert limit > 0, "Limit must be positive"

        collection = self.get_collection()
        query = {"username": {"$in": usernames}}

        # Add date filter if provided
        if min_date:
            query["created_at"] = {"$gte": min_date}

        # Ensure limit is an integer
        int_limit = int(limit)

        cursor = collection.find(query, sort=[("created_at", -1)], limit=int_limit)
        return await cursor.to_list(length=int_limit)

    async def delete_tweets_by_username(self, username: str) -> int:
        """Delete all tweets by a specific user."""
        assert username, "Username must not be empty"

        collection = self.get_collection()
        result = await collection.delete_many({"username": username})
        return result.deleted_count

    async def get_users(self, usernames: List[str]) -> List[Dict[str, Any]]:
        """Get multiple users from the database by their usernames in a single call.

        Args:
            usernames: List of usernames to fetch

        Returns:
            List of user documents
        """
        assert usernames, "Usernames list must not be empty"

        collection = self.get_users_collection()
        cursor = collection.find({"_id": {"$in": usernames}})
        return await cursor.to_list(length=len(usernames))
