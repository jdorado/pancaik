import asyncio
import os

from crewai_agent import TweetAgent
from dotenv import load_dotenv


async def main():
    """
    Demonstration of Pancaik agent capabilities using CrewAI TweetAgent
    """
    print("\n=== Starting CrewAI Tweet Agent Demo ===\n")

    load_dotenv()

    # Get API key from environment variable
    api_key = os.environ.get("OPENAI_API_KEY")

    # Create tweet agent
    tweet_agent = TweetAgent(id="crewai_tweet_agent", api_key=api_key)

    # Run create_tweet task directly
    result = await tweet_agent.run("create_tweet")
    print(f"Tweet created: {result['tweet'] if 'tweet' in result else 'No tweet generated'}")


# Add code to run the main function if this script is executed directly
if __name__ == "__main__":
    asyncio.run(main())
