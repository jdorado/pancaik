import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from pancaik import init
from pancaik.agents.TwitterAgent import TwitterAgent
from pancaik.core.config import logger

# Load environment variables
load_dotenv()

# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).parent


async def main():
    """Simple example of using the Twitter agent."""
    # X API service from https://github.com/jdorado/x-api-service - RESTful API wrapper for Twitter/X platform
    # Initialize the app with basic configuration
    app = await init(
        {
            "db_connection": os.getenv("MONGO_CONNECTION", "mongodb://localhost:27017/pancaik"),
            "x_api_url": os.getenv("X_API", "http://localhost:6011/api"),
        }
    )

    # Create the Twitter agent
    yaml_path = SCRIPT_DIR / "twitter_agent.yaml"
    agent = TwitterAgent(id="twitter_example", yaml_path=str(yaml_path), use_default_config=True)

    # Run a simple task - index our mentions
    logger.info("Running index_own_mentions task...")
    await agent.run("index_own_mentions")

    # Post something from our research
    logger.info("Running post_from_daily_research task...")
    await agent.run("post_from_daily_research")

    return app


if __name__ == "__main__":
    asyncio.run(main())
