"""Pancaik Agents package"""

import asyncio
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.routing import APIRouter

# Import services to register their tools
from . import services
from .core.agent import Agent
from .core.config import logger, set_config, update_config
from .core.db import init_db
from .core.task_runner import run_tasks

# Add the init function to the public API
__all__ = ["Agent", "init"]


async def run_continuous_tasks(parallel: bool = False, limit: int = 100, sleep_interval: int = 60):
    """Run tasks continuously with a sleep interval"""
    while True:
        try:
            await run_tasks(limit=limit, parallel=parallel)
            logger.info(f"Task runner going to sleep for {sleep_interval} seconds")
            await asyncio.sleep(sleep_interval)  # Sleep for configured interval between runs
        except Exception as e:
            logger.error(f"Task runner error: {str(e)}")
            logger.info(f"Task runner going to sleep for {sleep_interval} seconds before retry")
            await asyncio.sleep(sleep_interval)  # Sleep before retry on error


async def init(config: Optional[Dict[str, Any]] = None, app: Optional[FastAPI] = None):
    """
    Initialize the pancaik system with the provided configuration.

    Args:
        config: Dictionary with configuration options. Available options:
            Database Settings:
                - db_connection: MongoDB connection string (REQUIRED)

            Task Runner Settings:
                - run_continuous: Whether to run tasks continuously (default: False)
                - parallel: Whether to run tasks in parallel (default: False)
                - task_limit: Maximum number of tasks to process (default: 100)
                - sleep_interval: Seconds to sleep between task runs (default: 60)
                - add_tasks_endpoint: Whether to add the /tasks endpoint to the provided FastAPI app (default: False)

            Twitter Integration Settings:
                - x_api_url: URL for the X-API service (required for Twitter functionality)
                - twitter_concurrency: Maximum concurrent Twitter operations (default: 5)
                - twitter_max_concurrent_indexing_users: Maximum users to process in a single index_tweets call (default: 30)

        app: Optional FastAPI application to add routes to. Required if add_tasks_endpoint is True.

    Raises:
        ValueError: If required configuration parameters are missing
    """
    # Default config
    if config is None:
        config = {}

    # Check required configuration parameters
    required_params = ["db_connection"]
    missing_params = [param for param in required_params if param not in config]
    if missing_params:
        raise ValueError(f"Missing required configuration parameters: {', '.join(missing_params)}")

    # Update global configuration
    update_config(config)

    # Initialize and store database instance in config
    db = init_db(config["db_connection"])
    set_config("db", db)

    # Create Twitter semaphore for rate limiting
    twitter_concurrency = config.get("twitter_concurrency", 5)
    set_config("twitter_semaphore", asyncio.Semaphore(twitter_concurrency))

    # Set twitter_max_concurrent_indexing_users config
    twitter_max_concurrent_indexing_users = config.get("twitter_max_concurrent_indexing_users", 30)
    set_config("twitter_max_concurrent_indexing_users", twitter_max_concurrent_indexing_users)

    # Start continuous task runner if configured
    if config.get("run_continuous", False):
        task_limit = config.get("task_limit", 100)
        parallel = config.get("parallel", False)
        sleep_interval = config.get("sleep_interval", 60)
        asyncio.create_task(run_continuous_tasks(parallel=parallel, limit=task_limit, sleep_interval=sleep_interval))
        logger.info(f"Task runner started (limit={task_limit}, parallel={parallel}, sleep_interval={sleep_interval})")

    # Add tasks endpoint if requested and app is provided
    if app is not None and config.get("add_tasks_endpoint", False):
        router = APIRouter()

        @router.post("/tasks/")
        async def tasks_post():
            """
            Trigger an immediate task run using settings from config
            """
            limit = config.get("task_limit", 100)
            parallel = config.get("parallel", False)
            await run_tasks(limit=limit, parallel=parallel)
            return {"status": "success", "message": "Tasks executed"}

        app.include_router(router)
