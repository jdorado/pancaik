import asyncio
import os
from typing import Dict, Any, List

from init_env import init_env
from pancaik.core.agent import Agent
from pancaik.core.agent_handler import AgentHandler
from pancaik.core.config import logger


async def main():
    await init_env()

    # run specific task
    agent_id = "684af8eb3d788a390a8234a2"

    # Load agent config from the database
    logger.info(f"Loading agent config for ID: {agent_id}")
    agent_data = await AgentHandler.get_agent(agent_id)

    if agent_data:
        logger.info(f"Successfully loaded agent: {agent_data.get('name', 'Unknown')}")
    else:
        logger.error(f"Agent with ID {agent_id} not found in database")
        return

    # You can now use agent_data for further processing
    agent = Agent(id=agent_id, config=agent_data)
    #await agent.run(simulate=False)
    await agent.execute()

    return


if __name__ == "__main__":
    asyncio.run(main())
