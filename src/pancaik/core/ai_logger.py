"""
# Tools AI Logging Guidelines:
- Use ai_logger.thinking() for initial analysis and planning
- Use ai_logger.action() for significant operations being performed
- Use ai_logger.result() for outcomes and conclusions
- Keep standard logger.info/error for system-level logging
- AI logs should tell a story of the tool's thought process
- Focus on the main action/objective of the function, it's a narrative
- Always extract agent_id from data_store for AI logging context
- If the data store is missing, add it to the tools first.
- AI logging should focus on the AI elements and the tool's flow—log what the tool is doing, not system-level or unrelated errors. Only log exceptions if they are directly related to the tool's purpose or flow.
- Standard logger.info/error should be used for system-level logging

Example:
```python
from pancaik.core.ai_logger import ai_logger

# Get required IDs from data_store
agent_id = data_store.get("agent_id")
account_id = data_store.get("config", {}).get("account_id")
agent_name = data_store.get("config", {}).get("name")

ai_logger.thinking("Starting analysis...", agent_id, account_id, agent_name)
```
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorCollection

from .config import get_config


class AILogger:
    """Specialized logger for AI agents that shows thinking process."""

    _instance = None
    _lock = asyncio.Lock()
    _initialized = False
    _cleanup_task: Optional[asyncio.Task] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AILogger, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the AI logger."""
        # Only set instance variables if not already initialized
        if not hasattr(self, "_buffer"):
            self._buffer: List[Dict[str, Any]] = []
            self._max_buffer_size = 10  # Maximum number of logs to buffer before writing
            self._collection: Optional[AsyncIOMotorCollection] = None
            self._retention_days = 30  # Number of days to keep logs

    async def _ensure_initialized(self) -> None:
        """Ensure the logger is initialized with database connection."""
        if not self._initialized:
            async with self._lock:
                if not self._initialized:  # Double-check pattern
                    self.db = get_config("db")
                    if self.db is None:
                        return

                    self._collection = self.db["ai_thoughts"]
                    # Create indexes for better query performance
                    await self._collection.create_index([("timestamp", -1), ("agent_id", 1), ("account_id", 1)])

                    # Start the cleanup task
                    if self._cleanup_task is None:
                        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

                    self._initialized = True

    async def _cleanup_old_logs(self) -> None:
        """Delete logs older than retention period."""
        if self._collection is None:
            return

        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=self._retention_days)
            await self._collection.delete_many({"timestamp": {"$lt": cutoff_date}})
        except Exception:
            pass

    async def _periodic_cleanup(self) -> None:
        """Run cleanup periodically."""
        while True:
            try:
                await asyncio.sleep(24 * 60 * 60)  # Run once per day
                await self._cleanup_old_logs()
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(60)  # Wait a minute before retrying on error

    def set_retention_period(self, days: int) -> None:
        """Set the log retention period in days.

        Args:
            days: Number of days to keep logs
        """
        assert days > 0, "Retention period must be positive"
        self._retention_days = days

    def thinking(self, message: str, agent_id: str, account_id: str, agent_name: Optional[str] = None) -> None:
        """Log an AI thinking message.

        Args:
            message: The thinking process message
            agent_id: ID of the agent
            account_id: ID of the owner
            agent_name: Optional human-readable name of the agent
        """
        # Add to buffer
        log_entry = {
            "timestamp": datetime.now(timezone.utc),
            "message": message,
            "agent_id": agent_id,
            "account_id": account_id,
            "type": "thinking",
            "agent_name": agent_name,
        }

        self._buffer.append(log_entry)

        # If buffer is full, schedule a write
        if len(self._buffer) >= self._max_buffer_size:
            asyncio.create_task(self.flush())

    def action(self, message: str, agent_id: str, account_id: str, agent_name: Optional[str] = None) -> None:
        """Log an AI action message.

        Args:
            message: The action being taken
            agent_id: ID of the agent
            account_id: ID of the owner
            agent_name: Optional human-readable name of the agent
        """
        # Add to buffer
        log_entry = {
            "timestamp": datetime.now(timezone.utc),
            "message": message,
            "agent_id": agent_id,
            "account_id": account_id,
            "type": "action",
            "agent_name": agent_name,
        }

        self._buffer.append(log_entry)

        # If buffer is full, schedule a write
        if len(self._buffer) >= self._max_buffer_size:
            asyncio.create_task(self.flush())

    def result(self, message: str, agent_id: str, account_id: str, agent_name: Optional[str] = None) -> None:
        """Log an AI result message.

        Args:
            message: The result or conclusion
            agent_id: ID of the agent
            account_id: ID of the owner
            agent_name: Optional human-readable name of the agent
        """
        # Add to buffer
        log_entry = {
            "timestamp": datetime.now(timezone.utc),
            "message": message,
            "agent_id": agent_id,
            "account_id": account_id,
            "type": "result",
            "agent_name": agent_name,
        }

        self._buffer.append(log_entry)

        # If buffer is full, schedule a write
        if len(self._buffer) >= self._max_buffer_size:
            asyncio.create_task(self.flush())

    async def flush(self) -> None:
        """Flush the buffer to MongoDB."""
        if not self._buffer:
            return

        # Ensure we're initialized before attempting to write
        await self._ensure_initialized()

        async with self._lock:
            if not self._buffer:  # Double-check pattern
                return

            try:
                # Only write to database if we have a connection
                if self._collection is not None:
                    await self._collection.insert_many(self._buffer)
                # Clear the buffer regardless of whether we wrote to DB
                self._buffer.clear()
            except Exception:
                pass


# Global singleton instance
ai_logger = AILogger()
