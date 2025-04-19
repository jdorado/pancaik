import asyncio
import os

from dotenv import load_dotenv
from langgraph_agent import TweetAgent

from pancaik import init, run_server
from pancaik.core import TaskHandler


async def main():
    """
    Demonstration of Pancaik agent capabilities using TweetAgent
    """
    print("\n=== Starting Tweet Agent Demo ===\n")

    load_dotenv()

    # Get API key from environment variable
    api_key = os.environ.get("OPENAI_API_KEY")

    # Initialize pancaik with configuration
    app = await init({"run_continuous": True, "app_title": "Tweet Agent Demo"})

    # Clear all existing tasks from the database
    tasks_cleared = await TaskHandler.clear_all_tasks()
    print(f"Cleared {tasks_cleared} tasks from the database")

    # Create tweet agent
    tweet_agent = TweetAgent(id="tweet_agent", api_key=api_key)

    # Run create_tweet task directly
    result = await tweet_agent.run("create_tweet")
    print(f"Tweet created: {result['tweet']}")

    # Initialize agent tasks to tweet every minute
    await tweet_agent.init_tasks()

    return app


# Add code to run the main function if this script is executed directly
if __name__ == "__main__":
    app = asyncio.run(main())
    run_server(app, host="0.0.0.0", port=8080)
