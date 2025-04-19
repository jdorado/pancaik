"""
Task Handler module that centralizes all task-related database operations.
This provides a clean interface for working with tasks across the system.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .config import get_config, logger


class TaskHandler:
    """
    Handler for task-related database operations.
    Centralizes CRUD operations for tasks to minimize code duplication.
    """

    @staticmethod
    async def get_collection():
        """Get the tasks collection from the database"""
        db = get_config("db")
        assert db is not None, "Database must be initialized"
        return db.tasks

    @classmethod
    async def create_task(
        cls,
        task_name: str,
        agent_id: str,
        agent_class: str,
        next_run: datetime,
        params: Optional[Dict[str, Any]] = None,
        yaml_path: Optional[str] = None,
        use_default_config: bool = False,
    ) -> str:
        """
        Create or update a task in the database.

        Args:
            task_name: Name of the task to run
            agent_id: Unique identifier for the agent
            agent_class: Type of agent as a string
            next_run: Datetime when the task should run next
            params: Optional parameters for the task
            yaml_path: Optional path to the YAML configuration file
            use_default_config: Whether to use default configuration when instantiating the agent

        Returns:
            task_id: The unique identifier for the scheduled task
        """
        # Preconditions
        assert task_name and isinstance(task_name, str), "Task name must be a non-empty string"
        assert agent_id and isinstance(agent_id, str), "Agent ID must be a non-empty string"
        assert agent_class and isinstance(agent_class, str), "Agent class must be a non-empty string"
        assert isinstance(next_run, datetime), "Next run must be a datetime object"
        assert yaml_path is None or isinstance(yaml_path, str), "yaml_path must be a string if provided"
        assert isinstance(use_default_config, bool), "use_default_config must be a boolean"

        # Generate task_id by concatenating agent_id and task_name
        task_id = f"{agent_id}_{task_name}"

        # Create task document
        task_doc = {
            "task_id": task_id,
            "task_name": task_name,
            "agent_id": agent_id,
            "agent_class": agent_class,
            "next_run": next_run,
            "params": params or {},
            "yaml_path": yaml_path,
            "use_default_config": use_default_config,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "status": "scheduled",
        }

        # Save to database
        collection = await cls.get_collection()
        await collection.update_one({"task_id": task_id}, {"$set": task_doc}, upsert=True)

        # Postcondition
        assert await cls.task_exists(task_id), "Task was not successfully created in the database"

        logger.info(f"Created/updated task {task_id} to run at {next_run}")
        return task_id

    @classmethod
    async def get_task(cls, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a task by its ID.

        Args:
            task_id: The unique identifier for the task

        Returns:
            Task document or None if not found
        """
        # Precondition
        assert task_id and isinstance(task_id, str), "Task ID must be a non-empty string"

        collection = await cls.get_collection()
        task = await collection.find_one({"task_id": task_id})

        # Postcondition - if task found, it must have required fields
        if task:
            assert "task_id" in task, "Retrieved task must have a task_id field"
            assert "status" in task, "Retrieved task must have a status field"

        return task

    @classmethod
    async def get_agent_tasks(cls, agent_id: str) -> List[Dict[str, Any]]:
        """
        Get all tasks for a specific agent.

        Args:
            agent_id: Unique identifier for the agent

        Returns:
            List of task documents
        """
        # Precondition
        assert agent_id and isinstance(agent_id, str), "Agent ID must be a non-empty string"

        collection = await cls.get_collection()
        cursor = collection.find({"agent_id": agent_id})
        tasks = await cursor.to_list(length=None)

        # Postcondition
        for task in tasks:
            assert task["agent_id"] == agent_id, "All returned tasks must belong to the specified agent"

        return tasks

    @classmethod
    async def get_tasks_by_status(cls, status: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get tasks by their status.

        Args:
            status: Status to filter by (scheduled, running, completed, failed)
            limit: Maximum number of tasks to return

        Returns:
            List of task documents
        """
        # Preconditions
        assert status and isinstance(status, str), "Status must be a non-empty string"
        assert status in ["scheduled", "running", "completed", "failed"], "Status must be one of: scheduled, running, completed, failed"
        assert isinstance(limit, int) and limit > 0, "Limit must be a positive integer"

        collection = await cls.get_collection()
        cursor = collection.find({"status": status})
        cursor.sort("next_run", 1)
        cursor.limit(limit)

        tasks = await cursor.to_list(length=limit)

        # Postcondition
        for task in tasks:
            assert task["status"] == status, "All returned tasks must have the requested status"
        assert len(tasks) <= limit, "Number of returned tasks must not exceed the specified limit"

        return tasks

    @classmethod
    async def get_due_tasks(cls, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get tasks that are due to run (next_run <= now).

        Args:
            limit: Maximum number of tasks to return

        Returns:
            List of task documents
        """
        # Precondition
        assert isinstance(limit, int) and limit > 0, "Limit must be a positive integer"

        now = datetime.now()
        collection = await cls.get_collection()
        query = {"next_run": {"$lte": now}, "status": "scheduled"}

        cursor = collection.find(query)
        cursor.sort("next_run", 1)
        cursor.limit(limit)

        tasks = await cursor.to_list(length=limit)

        # Postcondition
        for task in tasks:
            assert task["status"] == "scheduled", "All returned tasks must have 'scheduled' status"
            assert task["next_run"] <= now, "All returned tasks must be due to run"
        assert len(tasks) <= limit, "Number of returned tasks must not exceed the specified limit"

        return tasks

    @classmethod
    async def update_task_status(cls, task_id: str, status: str, extra_fields: Optional[Dict[str, Any]] = None) -> None:
        """
        Update a task's status in the database.

        Args:
            task_id: ID of the task to update
            status: New status (scheduled, running, completed, failed)
            extra_fields: Additional fields to update
        """
        # Preconditions
        assert task_id and isinstance(task_id, str), "Task ID must be a non-empty string"
        assert status and isinstance(status, str), "Status must be a non-empty string"
        assert status in ["scheduled", "running", "completed", "failed"], "Status must be one of: scheduled, running, completed, failed"
        assert extra_fields is None or isinstance(extra_fields, dict), "Extra fields must be a dictionary or None"

        update_data = {"status": status, "updated_at": datetime.now(), f"{status}_at": datetime.now()}

        if extra_fields:
            update_data.update(extra_fields)

        collection = await cls.get_collection()
        result = await collection.update_one({"task_id": task_id}, {"$set": update_data})

        # Postcondition
        assert result.matched_count > 0, f"No task with ID {task_id} was found for status update"

        logger.info(f"Updated task {task_id} status to {status}")

    @classmethod
    async def delete_task(cls, task_id: str) -> bool:
        """
        Delete a task from the database.

        Args:
            task_id: ID of the task to delete

        Returns:
            True if the task was deleted, False if not found
        """
        # Precondition
        assert task_id and isinstance(task_id, str), "Task ID must be a non-empty string"

        collection = await cls.get_collection()
        result = await collection.delete_one({"task_id": task_id})

        # Postcondition: task should no longer exist if it was deleted
        if result.deleted_count > 0:
            assert not await cls.task_exists(task_id), "Task still exists after deletion"
            logger.info(f"Deleted task {task_id}")
            return True

        logger.warning(f"Task {task_id} not found for deletion")
        return False

    @classmethod
    async def delete_agent_tasks(cls, agent_id: str, task_names: Optional[List[str]] = None) -> int:
        """
        Delete tasks for a specific agent.

        Args:
            agent_id: Unique identifier for the agent
            task_names: Optional list of task names to delete.
                        If not provided, all tasks for the agent will be deleted.

        Returns:
            Number of tasks deleted
        """
        # Preconditions
        assert agent_id and isinstance(agent_id, str), "Agent ID must be a non-empty string"
        assert task_names is None or isinstance(task_names, list), "Task names must be a list or None"

        collection = await cls.get_collection()

        # Build query based on whether specific task names were provided
        query = {"agent_id": agent_id}
        if task_names:
            query["task_name"] = {"$in": task_names}

        # Delete matching tasks
        result = await collection.delete_many(query)
        deleted_count = result.deleted_count

        # Log the result
        if deleted_count > 0:
            task_str = f"specific tasks {task_names}" if task_names else "all tasks"
            logger.info(f"Deleted {deleted_count} {task_str} for agent {agent_id}")
        else:
            logger.warning(f"No tasks found to delete for agent {agent_id}")

        return deleted_count

    @classmethod
    async def clear_all_tasks(cls) -> int:
        """
        Clear all tasks from the database. Use with caution!

        Returns:
            Number of tasks deleted
        """
        # Get the collection
        collection = await cls.get_collection()

        # Count the number of tasks before deletion
        count_before = await cls.get_task_count()

        # Delete all tasks
        result = await collection.delete_many({})
        deleted_count = result.deleted_count

        # Postcondition: verify no tasks remain
        count_after = await cls.get_task_count()
        assert count_after == 0, "Tasks still remain after clear_all_tasks was called"

        # Log the result
        logger.warning(f"Cleared all {deleted_count} tasks from the database")

        return deleted_count

    @classmethod
    async def task_exists(cls, task_id: str) -> bool:
        """
        Check if a task exists in the database.

        Args:
            task_id: ID of the task to check

        Returns:
            True if the task exists, False otherwise
        """
        # Precondition
        assert task_id and isinstance(task_id, str), "Task ID must be a non-empty string"

        collection = await cls.get_collection()
        count = await collection.count_documents({"task_id": task_id}, limit=1)

        # Postcondition - the count must be either 0 or 1
        assert count in [0, 1], f"Invalid count result: {count}"

        return count > 0

    @classmethod
    async def get_task_count(cls, query: Optional[Dict[str, Any]] = None) -> int:
        """
        Get the count of tasks matching the query.

        Args:
            query: Optional query criteria for counting tasks

        Returns:
            Number of tasks matching the query
        """
        # Precondition
        assert query is None or isinstance(query, dict), "Query must be a dictionary or None"

        collection = await cls.get_collection()
        count = await collection.count_documents(query or {})

        # Postcondition - the count must be non-negative
        assert count >= 0, f"Invalid count result: {count}"

        return count

    @classmethod
    async def schedule_next_run(cls, task_id: str, minutes: int, retry_count: int = 0) -> str:
        """
        Schedule the next run for a task.

        Args:
            task_id: ID of the task to schedule
            minutes: Number of minutes from now to schedule the task
            retry_count: Number of times this task has been retried

        Returns:
            task_id of the scheduled task
        """
        # Preconditions
        assert task_id and isinstance(task_id, str), "Task ID must be a non-empty string"
        assert isinstance(minutes, int) and minutes > 0, "Minutes must be a positive integer"
        assert isinstance(retry_count, int) and retry_count >= 0, "retry_count must be a non-negative integer"

        # Get the existing task
        task = await cls.get_task(task_id)
        assert task is not None, f"Task with ID {task_id} not found"

        # Calculate the next run time
        next_run = datetime.now() + timedelta(minutes=minutes)

        # Update the task
        collection = await cls.get_collection()
        result = await collection.update_one(
            {"task_id": task_id},
            {
                "$set": {
                    "next_run": next_run,
                    "status": "scheduled",
                    "updated_at": datetime.now(),
                    "scheduled_at": datetime.now(),
                    "retry_count": retry_count,
                }
            },
        )

        # Postcondition
        assert result.matched_count > 0, f"Failed to update task {task_id}"

        logger.info(f"Scheduled next run for task {task_id} at {next_run} (retry count: {retry_count})")
        return task_id

    @classmethod
    async def schedule_task_runner(cls, minutes: int) -> str:
        """
        Schedule the task runner to run periodically.

        Args:
            minutes: Number of minutes between runs

        Returns:
            task_id of the scheduled task
        """
        # Precondition
        assert isinstance(minutes, int) and minutes > 0, "Minutes must be a positive integer"

        task_name = "run_tasks"
        agent_id = "system"
        agent_class = "TaskRunnerAgent"
        next_run = datetime.now() + timedelta(minutes=minutes)

        # Parameters for the task
        params = {"interval_minutes": minutes, "system_task": True}

        # Create or update the task
        task_id = await cls.create_task(task_name=task_name, agent_id=agent_id, agent_class=agent_class, next_run=next_run, params=params)

        # Postcondition
        task = await cls.get_task(task_id)
        assert task is not None, "Failed to schedule task runner"
        assert task["params"].get("system_task") is True, "Task runner must be marked as a system task"

        logger.info(f"Scheduled task runner to run every {minutes} minutes, starting at {next_run}")
        return task_id
