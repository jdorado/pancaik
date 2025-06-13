import asyncio
import os

KEYCHAIN_SECRETS = [
    ("ezenciel", "MONGO_CONNECTION", None),
    ("ezenciel", "ENCRYPTION_KEY", None),
    ("global", "OPENROUTER_API_KEY", None),
    ("global", "GEMINI_API_KEY", None),
]


def load_keychain_secrets():
    from keychain import load_secrets

    if not load_secrets(KEYCHAIN_SECRETS):
        raise ValueError("Failed to load some secrets from keychain")


# Load secrets before environment variables
load_keychain_secrets()

from pancaik import init
from pancaik.core.agent import Agent
from pancaik.core.agent_handler import AgentHandler
from pancaik.core.config import logger


async def main():
    config = {
        "db_connection": os.getenv("MONGO_CONNECTION", "mongodb://localhost:27017/pancaik"),
        "x_api_url": os.getenv("X_API", "http://localhost:6011/api"),
        "firecrawl_api_key": "fc-79e1e50bf0da4a4fbfcfd85de4dc4944",
        "twitter_consumer_key": "54BTR8j7PjAWPYFWn81iabC3L",
        "twitter_consumer_secret": "w2LrT4n2bqpQu4hYCRctggrH7hFfkVkpWU2hhNFAML95IBeIpQ",
        "twitter_bearer_token": "AAAAAAAAAAAAAAAAAAAAAATI2QEAAAAALTdiUe%2FF35XAtLHfT3327i8YfTc%3DkKmF0X9NCSKz9LuECvj6NLCu0IsX5UozvpvorweiUNNzaoZp9h",
    }
    await init(config)

    # run specific task
    agent_id = "684bffb42681b84d3d782372"

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
    await agent.run(simulate=False)
    # await agent.execute()

    return


if __name__ == "__main__":
    asyncio.run(main())
