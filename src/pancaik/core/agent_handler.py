"""
Agent Handler module that centralizes all agent-related database operations.
This provides a clean interface for working with agents across the system.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
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
    async def insert_agent(cls, agent_id: str, agent_data: Dict[str, Any], owner_id: Optional[str] = None) -> bool:
        """
        Insert a new agent into the database.

        Args:
            agent_id: The unique identifier for the agent as a string
            agent_data: Dictionary containing the agent data
            owner_id: Optional ID of the owner agent (for hierarchy)

        Returns:
            bool: True if insert was successful, False otherwise
        """
        # Precondition
        assert isinstance(agent_id, str), "Agent id must be a string"
        assert isinstance(agent_data, dict), "Agent data must be a dictionary"
        assert agent_data, "Agent data cannot be empty"
        assert "_id" not in agent_data, "Agent data should not contain _id field"
        assert owner_id is None or isinstance(owner_id, str), "Owner id must be a string or None"

        collection = await cls.get_collection()
        
        # Add creation timestamp and ensure UTC
        now = datetime.now(timezone.utc)
        agent_data.update({
            "created_at": now,
            "updated_at": now,
            "owner_id": owner_id  # Set owner_id (None for root agents)
        })

        try:
            # Insert the new agent
            result = await collection.insert_one({
                "_id": ObjectId(agent_id),
                **agent_data
            })
            return bool(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to insert agent {agent_id}: {str(e)}")
            return False

    @classmethod
    async def get_agent_descendants(cls, agent_id: str) -> List[str]:
        """
        Get all descendants of an agent by recursively following owner_id references.

        Args:
            agent_id: The root agent ID to start from

        Returns:
            List of descendant agent IDs
        """
        collection = await cls.get_collection()
        
        # Find all agents that have this agent as an owner
        descendants = []
        async for agent in collection.find({"owner_id": agent_id}):
            descendants.append(str(agent["_id"]))
            # Recursively get descendants of this child
            descendants.extend(await cls.get_agent_descendants(str(agent["_id"])))
            
        return descendants

    @classmethod
    async def delete_agent(cls, agent_id: str) -> bool:
        """
        Delete an agent from the database.

        Args:
            agent_id: The ID of the agent to delete

        Returns:
            bool: True if deletion was successful
        """
        collection = await cls.get_collection()
        
        # Delete the agent
        result = await collection.delete_one({"_id": ObjectId(agent_id)})
        return result.deleted_count > 0

    @classmethod
    async def deactivate_agent_hierarchy(cls, agent_id: str) -> List[str]:
        """
        Deactivate an agent and delete all its descendants.
        The root agent is deactivated but preserved, while all descendants are deleted.

        Args:
            agent_id: The root agent ID to start from

        Returns:
            List of affected agent IDs (deleted descendants + deactivated root)
        """
        # First get all descendants
        descendants = await cls.get_agent_descendants(agent_id)
        affected = []
        
        # Delete all descendants
        for desc_id in descendants:
            if await cls.delete_agent(desc_id):
                affected.append(desc_id)
                logger.info(f"Deleted descendant agent {desc_id}")
            else:
                logger.warning(f"Failed to delete descendant agent {desc_id}")
        
        # Deactivate the root agent (but don't delete it)
        await cls.update_agent_status(agent_id, "completed", {"is_active": False})
        affected.append(agent_id)
        logger.info(f"Deactivated root agent {agent_id}")
        
        return affected

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
        Update an agent's fields in the database. If the agent doesn't exist, creates it.

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
        
        # Add updated_at timestamp
        now = datetime.now(timezone.utc)
        update_data["updated_at"] = now
        
        # If this is a new document, also set created_at
        result = await collection.update_one(
            {"_id": ObjectId(agent_id)},
            {
                "$set": update_data,
                "$setOnInsert": {"created_at": now}
            },
            upsert=True
        )

        # Postcondition
        assert result.matched_count in [0, 1], "Update should match at most one document"
        
        return result.modified_count > 0 or result.upserted_id is not None

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

    @classmethod
    async def get_sub_agents_by_steps(cls, owner_id: str, step_requirements: List[Tuple[str, str]]) -> Dict[Tuple[str, str], str]:
        """
        Get active sub-agents for specific step requirements.

        Args:
            owner_id: The ID of the owner agent
            step_requirements: List of tuples (step_id, required_agent)

        Returns:
            Dictionary mapping (step_id, required_agent) to agent_id for found agents
        """
        # Precondition
        assert isinstance(owner_id, str), "Owner id must be a string"
        assert isinstance(step_requirements, list), "Step requirements must be a list"
        assert all(isinstance(t, tuple) and len(t) == 2 for t in step_requirements), "Each requirement must be a (step_id, required_agent) tuple"
        assert len(step_requirements) > 0, "At least one requirement must be provided"

        # Create query conditions for each requirement
        conditions = []
        for step_id, required_agent in step_requirements:
            conditions.append({
                "owner_id": owner_id,
                "step_id": step_id,
                "required_agent": required_agent,
                "is_active": True
            })

        collection = await cls.get_collection()
        cursor = collection.find({"$or": conditions})

        # Create mapping of (step_id, required_agent) -> agent_id
        result = {}
        async for agent in cursor:
            key = (agent["step_id"], agent["required_agent"])
            result[key] = str(agent["_id"])

        return result

    @classmethod
    async def ensure_indexes(cls):
        """Ensure required indexes exist in the database"""
        collection = await cls.get_collection()
        
        # Create compound unique index
        await collection.create_index(
            [
                ("owner_id", 1),
                ("step_id", 1),
                ("required_agent", 1)
            ],
            unique=True,
            background=True
        ) 