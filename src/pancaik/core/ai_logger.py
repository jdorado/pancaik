"""
# Tools AI Logging Guidelines:
- Use ai_logger.thinking() for initial analysis and planning
- Use ai_logger.action() for significant operations being performed
- Use ai_logger.result() for outcomes and conclusions
- Use ai_logger.warning() for potential issues that need attention but aren't errors
- Use ai_logger.error() for user-facing errors that should be displayed/handled
- Keep standard logger.info/error for system-level logging
- AI logs should tell a story of the tool's thought process
- Focus on the main action/objective of the function, it's a narrative
- Always extract agent_id from data_store for AI logging context
- If the data store is missing, add it to the tools first.
- AI logging should focus on the AI elements and the tool's flow—log what the tool is doing, not system-level or unrelated errors. Only log exceptions if they are directly related to the tool's purpose or flow.
- Standard logger.info/error should be used for system-level logging
- **Do NOT log long strings or large data (such as prompts, full documents, or large payloads). Instead, log only keys, names, IDs, or summaries. Logging large content makes logs unwieldy and less useful.**

Example:
```python
from pancaik.core.ai_logger import ai_logger

# Get required IDs from data_store
agent_id = data_store.get("agent_id")
account_id = data_store.get("config", {}).get("account_id")
agent_name = data_store.get("config", {}).get("name")

# Example of different log types
ai_logger.thinking("Starting analysis...", agent_id, account_id, agent_name)
ai_logger.warning("Resource usage at 80% threshold", agent_id, account_id, agent_name)
```
"""

import asyncio
import atexit
import logging
import logging.handlers
import queue
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import pymongo
from motor.motor_asyncio import AsyncIOMotorCollection

from .config import get_config, logger


class AILogger:
    """Specialized logger for AI agents that shows thinking process with automatic flushing."""

    _instance = None
    _lock = asyncio.Lock()
    _initialized = False
    _cleanup_task: Optional[asyncio.Task] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AILogger, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the AI logger with QueueHandler for non-blocking logging."""
        # Only set instance variables if not already initialized
        if not hasattr(self, "_queue"):
            self._queue = queue.Queue(-1)  # Unlimited size queue
            self._queue_handler = logging.handlers.QueueHandler(self._queue)
            self._queue_listener: Optional[logging.handlers.QueueListener] = None
            self._collection: Optional[AsyncIOMotorCollection] = None
            self._retention_days = 30  # Number of days to keep logs

            # Flush frequency control (similar to old buffer size)
            self._message_count = 0
            self._flush_frequency = 10  # Flush every N messages (like old buffer size)
            self._immediate_mode = False  # When True, bypass queue and write immediately
            self._debug_mode = False

            self._setup_queue_logging()

    def _setup_queue_logging(self) -> None:
        """Set up QueueListener with MongoDB handler for automatic flushing."""
        # Create a custom handler that writes to MongoDB
        mongodb_handler = MongoDBHandler(self)

        # Create QueueListener with MongoDB handler
        self._queue_listener = logging.handlers.QueueListener(self._queue, mongodb_handler, respect_handler_level=True)

        # Start the listener thread
        self._queue_listener.start()

        # Register cleanup on exit - this ensures flushing on program termination
        atexit.register(self._cleanup_on_exit)

    def _cleanup_on_exit(self) -> None:
        """Cleanup function called on program exit."""
        if self._queue_listener:
            self._queue_listener.stop()

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

    def set_flush_frequency(self, frequency: int) -> None:
        """Set how often to force flush queued messages.

        Args:
            frequency: Flush every N messages (1 = immediate, 10 = every 10 messages, etc.)
        """
        assert frequency > 0, "Flush frequency must be positive"
        self._flush_frequency = frequency

    def set_debug_mode(self, enabled: bool) -> None:
        """Enable or disable debug mode for verbose logging."""
        self._debug_mode = enabled

    def set_immediate_mode(self, enabled: bool) -> None:
        """Enable or disable immediate mode.

        When enabled, messages bypass the queue and are written directly to MongoDB.
        This provides true immediate flushing but is blocking.

        Args:
            enabled: True for immediate writes, False for queued writes
        """
        self._immediate_mode = enabled

    def _log_message(self, log_type: str, message: str, agent_id: str, account_id: str, agent_name: Optional[str] = None) -> None:
        """Internal method to log messages using QueueHandler.

        Args:
            log_type: Type of log (thinking, action, result, warning, error)
            message: The log message
            agent_id: ID of the agent
            account_id: ID of the owner
            agent_name: Optional human-readable name of the agent
        """
        # Ensure initialization happens on first use
        if not self._initialized:
            # Schedule initialization to happen soon
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._ensure_initialized())
            except RuntimeError:
                # No event loop running, initialization will happen later
                pass

        # Create log entry
        log_entry = {
            "timestamp": datetime.now(timezone.utc),
            "message": message,
            "agent_id": agent_id,
            "account_id": account_id,
            "type": log_type,
            "agent_name": agent_name,
        }

        # Add user-facing flag for warnings and errors
        if log_type in ("warning", "error"):
            log_entry["is_user_facing"] = True

        logger.info(f"AI {log_type.title()} [{agent_id}]: {message}")

        # Check if immediate mode is enabled
        if self._immediate_mode:
            # Write directly to MongoDB bypassing the queue
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._write_immediate(log_entry))
            except RuntimeError:
                # No event loop, fall back to queue
                self._queue_handler.emit(AILogRecord(log_entry))
        else:
            # Use QueueHandler to log - this automatically handles flushing on exceptions
            # The queue listener will process this in a separate thread
            try:
                ai_log_record = AILogRecord(log_entry)
                self._queue_handler.emit(ai_log_record)

                # Increment message count and check if we should force a flush
                self._message_count += 1
                if self._flush_frequency == 1 or self._message_count >= self._flush_frequency:
                    # Reset counter and schedule a flush
                    self._message_count = 0
                    # Force a small delay to ensure queued messages are processed
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(self._force_flush())
                    except RuntimeError:
                        # No event loop, flush will happen naturally
                        pass

            except Exception as e:
                # Fallback to direct logging if queue fails
                logger.error(f"Failed to queue AI log message: {e}")

    async def _write_immediate(self, log_entry: Dict[str, Any]) -> None:
        """Write log entry immediately to MongoDB."""
        try:
            # Ensure we're initialized
            if not self._initialized:
                await self._ensure_initialized()

            if self._collection is not None:
                await self._collection.insert_one(log_entry)
        except Exception as e:
            logger.error(f"Failed to write immediate AI log: {e}")

    async def _force_flush(self) -> None:
        """Force a flush by adding a small delay."""
        await asyncio.sleep(0.05)  # Small delay to ensure messages are processed

    def thinking(self, message: str, agent_id: str, account_id: str, agent_name: Optional[str] = None) -> None:
        """Log an AI thinking message.

        Args:
            message: The thinking process message
            agent_id: ID of the agent
            account_id: ID of the owner
            agent_name: Optional human-readable name of the agent
        """
        self._log_message("thinking", message, agent_id, account_id, agent_name)

    def action(self, message: str, agent_id: str, account_id: str, agent_name: Optional[str] = None) -> None:
        """Log an AI action message.

        Args:
            message: The action being taken
            agent_id: ID of the agent
            account_id: ID of the owner
            agent_name: Optional human-readable name of the agent
        """
        self._log_message("action", message, agent_id, account_id, agent_name)

    def result(self, message: str, agent_id: str, account_id: str, agent_name: Optional[str] = None) -> None:
        """Log an AI result message.

        Args:
            message: The result or conclusion
            agent_id: ID of the agent
            account_id: ID of the owner
            agent_name: Optional human-readable name of the agent
        """
        self._log_message("result", message, agent_id, account_id, agent_name)

    def error(self, message: str, agent_id: str, account_id: str, agent_name: Optional[str] = None) -> None:
        """Log an AI error message that should be shown to users.

        Args:
            message: The user-facing error message
            agent_id: ID of the agent
            account_id: ID of the owner
            agent_name: Optional human-readable name of the agent
        """
        self._log_message("error", message, agent_id, account_id, agent_name)

    def warning(self, message: str, agent_id: str, account_id: str, agent_name: Optional[str] = None) -> None:
        """Log an AI warning message for potential issues that need attention.

        Args:
            message: The warning message
            agent_id: ID of the agent
            account_id: ID of the owner
            agent_name: Optional human-readable name of the agent
        """
        self._log_message("warning", message, agent_id, account_id, agent_name)

    async def flush(self) -> None:
        """Flush any remaining messages.

        Note: With QueueListener, this is largely automatic, but we provide this
        for compatibility and to ensure any remaining messages are processed.
        """
        # Ensure we're initialized
        if not self._initialized:
            await self._ensure_initialized()

        # The QueueListener automatically handles flushing, but we can add a small delay
        # to ensure any pending messages are processed
        await asyncio.sleep(0.1)

    async def test_connection(self) -> bool:
        """Test if the logger can connect to MongoDB.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            await self._ensure_initialized()
            if self._collection is not None:
                # Try a simple operation to test connection
                await self._collection.count_documents({}, limit=1)
                return True
            return False
        except Exception as e:
            logger.warning(f"AI Logger connection test failed: {e}")
            return False


class AILogRecord(logging.LogRecord):
    """Custom LogRecord for AI logging."""

    def __init__(self, log_data: Dict[str, Any]):
        # Create a minimal LogRecord
        super().__init__(name="ai_logger", level=logging.INFO, pathname="", lineno=0, msg=log_data["message"], args=(), exc_info=None)
        # Store the AI log data
        self.ai_log_data = log_data


class MongoDBHandler(logging.Handler):
    """Custom logging handler that writes AI logs to MongoDB."""

    def __init__(self, ai_logger_instance: AILogger):
        super().__init__()
        self.ai_logger = ai_logger_instance
        self._sync_collection = None

    def _get_sync_collection(self):
        """Get a synchronous collection using the database connection string from config."""
        if self._sync_collection is None:
            try:
                # Get the database connection string from the existing config
                db_connection = get_config("db_connection")
                if db_connection and self.ai_logger._collection is not None:
                    sync_client = pymongo.MongoClient(db_connection)
                    # Use the same database and collection name as the async version
                    db_name = self.ai_logger._collection.database.name
                    collection_name = self.ai_logger._collection.name
                    sync_db = sync_client[db_name]
                    self._sync_collection = sync_db[collection_name]
            except Exception as e:
                print(f"AI Logger: Failed to create sync collection: {e}", file=sys.stderr)
        return self._sync_collection

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to MongoDB using synchronous operations."""
        try:
            if hasattr(record, "ai_log_data"):
                # This is an AI log record, write to MongoDB synchronously
                sync_collection = self._get_sync_collection()
                if sync_collection is not None:
                    try:
                        result = sync_collection.insert_one(record.ai_log_data)
                        # Only print success in debug mode
                        if hasattr(self.ai_logger, "_debug_mode") and self.ai_logger._debug_mode:
                            print(f"AI Logger: Successfully wrote log to MongoDB: {result.inserted_id}", file=sys.stderr)
                    except Exception as e:
                        print(f"AI Logger: MongoDB write error: {e}", file=sys.stderr)
        except Exception as e:
            print(f"AI Logger emit error: {e}", file=sys.stderr)


# Global singleton instance
ai_logger = AILogger()
