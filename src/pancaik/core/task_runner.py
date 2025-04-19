import asyncio
from typing import Any, Dict

from .agent import Agent
from .config import logger
from .task_handler import TaskHandler


async def run_tasks(limit: int = 1, parallel: bool = False) -> None:
    """
    Run tasks that are due for execution.

    Args:
        limit: Maximum number of tasks to process
        parallel: If True, runs tasks in parallel. If False, runs sequentially.
    """
    # Precondition: limit must be positive
    assert limit > 0, "Task limit must be a positive integer"

    # Get tasks that are due to run
    task_list = await TaskHandler.get_due_tasks(limit)

    # Invariant: task_list should be a list
    assert isinstance(task_list, list), "Expected task_list to be a list"

    if not task_list:
        logger.info("No tasks to run")
        return

    if parallel:
        await asyncio.gather(*[execute_task(task) for task in task_list])
    else:
        for task in task_list:
            await execute_task(task)


async def execute_task(task: Dict[str, Any]) -> None:
    """Execute a single task"""
    # Precondition: task must be a dictionary with required fields
    assert isinstance(task, dict), "Task must be a dictionary"
    assert "task_id" in task, "Task missing required field 'task_id'"
    assert "task_name" in task, "Task missing required field 'task_name'"
    assert "agent_id" in task, "Task missing required field 'agent_id'"
    assert "agent_class" in task, "Task missing required field 'agent_class'"
    assert "params" in task, "Task missing required field 'params'"

    task_id = task["task_id"]
    task_name = task["task_name"]
    agent_id = task["agent_id"]
    agent_class = task["agent_class"]
    params = task["params"]
    retry_count = task.get("retry_count", 0)
    yaml_path = task.get("yaml_path")
    use_default_config = task.get("use_default_config", False)

    # Invariant: params should be a dictionary
    assert isinstance(params, dict), "Task params must be a dictionary"
    # Invariant: retry_count must be a non-negative integer
    assert isinstance(retry_count, int) and retry_count >= 0, "retry_count must be a non-negative integer"
    # Invariant: use_default_config must be a boolean
    assert isinstance(use_default_config, bool), "use_default_config must be a boolean"
    # Invariant: yaml_path must be a string or None
    assert yaml_path is None or isinstance(yaml_path, str), "yaml_path must be a string or None"

    logger.info(f"Executing task {task_id}: {task_name} for agent {agent_id}")

    # Mark task as running
    await TaskHandler.update_task_status(task_id, "running")

    try:
        # Create agent configuration with appropriate parameters
        agent_config = {"class": agent_class, "id": agent_id, "yaml_path": yaml_path, "use_default_config": use_default_config}

        # Create agent instance and run task
        agent = Agent.from_config(agent_config)

        # Postcondition: agent must be an instance of Agent
        assert isinstance(agent, Agent), "Failed to create a valid Agent instance"

        result = await agent.run(task_name, **params)

        # Mark task as complete
        await TaskHandler.update_task_status(task_id, "completed", {"result": result or {}})

        # Use the agent's own scheduler to schedule the next run
        # This will use the scheduler configuration from the agent's task definition
        await agent.schedule_task(task_name, params=params)

        return result
    except Exception as e:
        error_message = f"{task_id}: {str(e)}"
        logger.error(error_message)

        # Increment retry count
        retry_count += 1

        # Mark task as failed with retry information
        await TaskHandler.update_task_status(task_id, "failed", {"error": str(e), "retry_count": retry_count})

        # Get retry policy from the agent's task definition
        retry_policy = None
        if task_name in agent.tasks:
            task_config = agent.tasks[task_name]
            retry_policy = task_config.get("retry_policy")

        # Default retry policy: retry in 10 minutes
        retry_minutes = 10
        max_retries = 5  # Maximum number of retry attempts

        # If retry_policy is explicitly set to None or False, don't retry
        if retry_policy is False:
            logger.info(f"Task {task_id} has retry_policy=False, not scheduling retry")
            return None

        # If retry_policy is a dict, check for minutes and max_retries parameters
        if isinstance(retry_policy, dict):
            if "minutes" in retry_policy:
                retry_minutes = retry_policy["minutes"]
            if "max_retries" in retry_policy:
                max_retries = retry_policy["max_retries"]

        # Invariant: retry_minutes must be non-negative
        assert retry_minutes >= 0, "Retry minutes must be a non-negative value"
        # Invariant: max_retries must be non-negative
        assert max_retries >= 0, "Max retries must be a non-negative value"

        # Check if we've reached the maximum number of retries
        if retry_count >= max_retries:
            logger.info(f"Task {task_id} has reached maximum retry attempts ({max_retries}), not scheduling retry")
            return None

        # Schedule next run based on retry policy
        await TaskHandler.schedule_next_run(task_id, minutes=retry_minutes, retry_count=retry_count)
        logger.info(f"Scheduled retry for task {task_id} (attempt {retry_count}/{max_retries}) in {retry_minutes} minutes")


if __name__ == "__main__":
    # Run the task runner
    asyncio.run(run_tasks())
