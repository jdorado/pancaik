import asyncio

from .agent import Agent
from .agent_handler import AgentHandler
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
        await asyncio.gather(*[agent.execute() for agent in agent_list])
    else:
        for agent in agent_list:
            await agent.execute()


