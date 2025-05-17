"""
Knowledge tools for agents.

This module provides tools for loading and managing knowledge content.
"""

from typing import Any, Dict, Optional

from bson import ObjectId
from pymongo.collection import Collection
from pymongo.database import Database

from ..core.ai_logger import ai_logger
from ..core.config import get_config, logger
from ..tools.base import tool


class KnowledgeHandler:
    """Handler for managing knowledge objects in the database."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize the knowledge handler.

        Args:
            db: Optional database instance. If not provided, will get from config when needed.
        """
        self._db = db

    def _ensure_db(self) -> Database:
        """Ensure we have a database connection."""
        if self._db is None:
            self._db = get_config("db")
            assert self._db is not None, "Database not initialized. Call init() first."
        return self._db

    def get_collection(self) -> Collection:
        """Get the knowledge collection."""
        return self._ensure_db().knowledge

    async def get_knowledge(self, knowledge_id: str) -> Optional[Dict[str, Any]]:
        """Get a knowledge entity by its ID."""
        assert knowledge_id, "Knowledge ID cannot be empty"
        collection = self.get_collection()
        knowledge = await collection.find_one({"_id": ObjectId(knowledge_id)})
        if not knowledge:
            logger.warning(f"Knowledge not found: {knowledge_id}")
            return None
        return knowledge


@tool
async def knowledge_loader(knowledge_id: str, data_store: Dict[str, Any]):
    """
    Loads knowledge by knowledge_id and adds it to the agent's context.

    Args:
        knowledge_id: The unique identifier of the knowledge to load
        data_store: Agent's data store containing configuration and state

    Returns:
        Dictionary with loaded knowledge in 'values' for context update, where context is a dict
        mapping the value of 'title' in params to the value of 'content'.
    """
    assert knowledge_id, "knowledge_id must be provided"
    assert data_store is not None, "data_store must be provided"
    agent_id = data_store.get("agent_id")
    account_id = data_store.get("config", {}).get("account_id")
    agent_name = data_store.get("config", {}).get("name")

    logger.info(f"Loading knowledge for agent {agent_id} with knowledge_id: {knowledge_id}")

    handler = KnowledgeHandler()
    knowledge = await handler.get_knowledge(knowledge_id)
    if knowledge is None:
        logger.warning(f"Knowledge not found for id: {knowledge_id}")
        ai_logger.warning(f"Knowledge not found for id: {knowledge_id}", agent_id, account_id, agent_name)
        return {}

    assert "params" in knowledge, "Knowledge document must have 'params' field"
    params = knowledge["params"]
    assert isinstance(params, dict), "Knowledge 'params' must be a dictionary"
    assert "title" in params and "content" in params, "Params must have 'title' and 'content' fields"

    # Build context: key = value of 'title', value = value of 'content'
    context = {params["title"]: params["content"]}
    ai_logger.result(f"Knowledge loaded and added to context for agent {agent_id}", agent_id, account_id, agent_name)
    logger.info(f"Knowledge loaded and added to context for agent {agent_id}")

    return {"values": {"context": context}}
