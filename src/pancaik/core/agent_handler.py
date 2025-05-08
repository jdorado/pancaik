"""
Agent Handler module that centralizes all agent-related database operations.
This provides a clean interface for working with agents across the system.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from bson import ObjectId

from .config import get_config, logger


class AgentHandler:
    """
    Handler for agent-related database operations.
    Centralizes CRUD operations for agents to minimize code duplication.
    """

    @staticmethod
    async def get_collection():
        """Get the agents collection from the database"""
        db = get_config("db")
        assert db is not None, "Database must be initialized"
        return db.agents

    @classmethod
    async def get_agent(cls, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get an agent by its ID.

        Args:
            agent_id: The unique identifier for the agent as a string.

        Returns:
            Agent document or None if not found
        """
        # Precondition: agent_id must be a string
        assert isinstance(agent_id, str), "Agent id must be a string"

        collection = await cls.get_collection()
        agent = await collection.find_one({"_id": ObjectId(agent_id)})

        # Ensure datetime fields are UTC-aware
        if agent:
            agent = cls._ensure_utc_datetime(agent)
            assert "_id" in agent, "Retrieved agent must have an _id field"

        return agent

    @staticmethod
    def _ensure_utc_datetime(data: Any) -> Any:
        """Recursively ensure all datetime values in the data structure are UTC-aware.
        
        Args:
            data: Any data structure that might contain datetime objects
            
        Returns:
            The data structure with all datetime objects converted to UTC-aware
        """
        if isinstance(data, datetime):
            # Convert naive datetime to UTC
            if data.tzinfo is None:
                return data.replace(tzinfo=timezone.utc)
            return data
        elif isinstance(data, dict):
            return {k: AgentHandler._ensure_utc_datetime(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [AgentHandler._ensure_utc_datetime(item) for item in data]
        elif isinstance(data, tuple):
            return tuple(AgentHandler._ensure_utc_datetime(item) for item in data)
        return data

    @classmethod
    async def get_due_tasks(cls, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get agents that are due to run (next_run <= now) and have state 'scheduled'.

        Args:
            limit: Maximum number of agents to return

        Returns:
            List of agent documents that are scheduled and due for execution
        """
        # Precondition
        assert isinstance(limit, int) and limit > 0, "Limit must be a positive integer"

        now = datetime.now(timezone.utc)
        collection = await cls.get_collection()
        query = {
            "next_run": {"$lte": now},
            "status": "scheduled",
            "is_active": True
        }

        cursor = collection.find(query)
        cursor.sort("next_run", 1)
        cursor.limit(limit)

        agents = await cursor.to_list(length=limit)
        
        # Ensure all datetime fields are UTC-aware
        agents = cls._ensure_utc_datetime(agents)

        # Postcondition
        for agent in agents:
            assert agent["status"] == "scheduled", "All returned agents must have 'scheduled' status"
            assert agent["next_run"] <= now, "All returned agents must be due to run"
        assert len(agents) <= limit, "Number of returned agents must not exceed the specified limit"

        return agents

    @classmethod
    async def update_agent(cls, agent_id: str, update_data: Dict[str, Any]) -> bool:
        """
        Update an agent's fields in the database.

        Args:
            agent_id: The unique identifier for the agent as a string
            update_data: Dictionary containing the fields to update

        Returns:
            bool: True if update was successful, False otherwise
        """
        # Precondition
        assert isinstance(agent_id, str), "Agent id must be a string"
        assert isinstance(update_data, dict), "Update data must be a dictionary"
        assert update_data, "Update data cannot be empty"

        collection = await cls.get_collection()
        result = await collection.update_one(
            {"_id": ObjectId(agent_id)},
            {"$set": update_data}
        )

        # Postcondition
        assert result.matched_count in [0, 1], "Update should match at most one document"
        
        return result.modified_count > 0

    @classmethod
    async def update_agent_status(cls, agent_id: str, status: str, extra_fields: Optional[Dict[str, Any]] = None) -> None:
        """
        Update an agent's status in the database.

        Args:
            agent_id: ID of the agent to update
            status: New status (running, completed, failed)
            extra_fields: Additional fields to update
        """
        # Preconditions
        assert agent_id and isinstance(agent_id, str), "Agent id must be a non-empty string"
        assert status and isinstance(status, str), "Status must be a non-empty string"
        assert status in ["scheduled", "running", "completed", "failed"], "Status must be one of: scheduled, running, completed, failed"
        assert extra_fields is None or isinstance(extra_fields, dict), "Extra fields must be a dictionary or None"

        now = datetime.now(timezone.utc)
        update_data = {"status": status, "updated_at": now}

        if extra_fields:
            update_data.update(extra_fields)

        await cls.update_agent(agent_id, update_data)
        logger.info(f"Updated agent {agent_id} status to {status}") 