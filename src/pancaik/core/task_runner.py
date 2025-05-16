import asyncio
from datetime import datetime, timedelta, timezone

from .agent import Agent
from .agent_handler import AgentHandler
from .ai_logger import ai_logger
from .config import logger


async def run_tasks(limit: int = 1, parallel: bool = False) -> None:
    """
    Run tasks that are due for execution.

    Args:
        limit: Maximum number of tasks to process
        parallel: If True, runs tasks in parallel. If False, runs sequentially.
    """
    # Precondition: limit must be positive
    assert limit > 0, "Task limit must be a positive integer"

    # Get agents that are due to run
    agent_docs = await AgentHandler.get_due_tasks(limit)

    # Invariant: agent_docs should be a list
    assert isinstance(agent_docs, list), "Expected agent_docs to be a list"

    if not agent_docs:
        logger.info("No agents to run")
        return

    # Convert agent documents to Agent instances
    agent_list = []
    for doc in agent_docs:
        # Extract id and config from document
        agent_id = str(doc["_id"])

        # Create Agent instance
        agent = Agent(id=agent_id, config=doc)
        agent_list.append(agent)

    if parallel:
        await asyncio.gather(*[execute_task(agent) for agent in agent_list])
    else:
        for agent in agent_list:
            await execute_task(agent)


async def execute_task(agent: Agent) -> None:
    """
    Execute a single agent's task.

    Args:
        agent: The agent instance to execute
    """
    # Precondition: agent must be a valid Agent instance
    assert isinstance(agent, Agent), "Must provide a valid Agent instance"

    agent_id = agent.id
    logger.info(f"Executing agent {agent_id}")

    # Mark agent as running
    await AgentHandler.update_agent_status(agent_id, "running")

    try:
        # Run the agent
        result = await agent.run()

        # Update agent status with successful completion and last run time
        current_time = datetime.now(timezone.utc)
        await AgentHandler.update_agent_status(
            agent_id, "completed", {"last_run": current_time, "error": None, "retry_count": 0, "next_run": None}
        )

        # Schedule next run
        await agent.schedule_next_run(last_run=current_time)

        return result
    except Exception as e:
        error_message = f"{agent_id}: {str(e)}"
        logger.error(error_message)

        retry_count = agent.retry_count + 1
        retry_policy = agent.retry_policy
        current_time = datetime.now(timezone.utc)

        # Default retry policy values - always retry unless explicitly disabled
        retry_minutes = 10
        max_retries = 5

        # Only skip retries if retry_policy is explicitly False
        if retry_policy is False:
            logger.info(f"Agent {agent_id} has retry_policy=False, not scheduling retry")
            await AgentHandler.update_agent_status(
                agent_id, "failed", {"error": str(e), "retry_count": retry_count, "next_run": None, "is_active": False}
            )
            return None

        # If retry_policy is a dict, check for custom minutes and max_retries parameters
        if isinstance(retry_policy, dict):
            retry_minutes = retry_policy.get("minutes", retry_minutes)
            max_retries = retry_policy.get("max_retries", max_retries)

        # Invariant: retry parameters must be non-negative
        assert retry_minutes >= 0, "Retry minutes must be a non-negative value"
        assert max_retries >= 0, "Max retries must be a non-negative value"

        # Check if we've reached the maximum number of retries
        if retry_count >= max_retries:
            logger.info(f"Agent {agent_id} has reached maximum retry attempts ({max_retries}), not scheduling retry")
            await agent.deactivate() # In order to stop any sub-agents
            await AgentHandler.update_agent_status(
                agent_id, "failed", {"error": str(e), "retry_count": retry_count, "next_run": None, "is_active": False}
            )
            return None

        # Schedule next run and update status with retry information
        await AgentHandler.update_agent_status(
            agent_id,
            "scheduled",
            {"error": str(e), "retry_count": retry_count, "next_run": current_time + timedelta(minutes=retry_minutes)},
        )
        logger.info(f"Scheduled retry for agent {agent_id} (attempt {retry_count}/{max_retries}) in {retry_minutes} minutes")
    finally:
        # Flush any buffered AI logs
        await ai_logger.flush()
