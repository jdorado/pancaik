import asyncio
import sys
from pathlib import Path

# Add src directory to path
src_path = str(Path(__file__).parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from greeter_agent import GreetingAgent


async def main():
    # Create agent
    greeter = GreetingAgent(id="demo_greeter")

    # Run various greeting tasks
    await greeter.run("greet", name="Alice")
    await greeter.run("greet_share_time", name="Bob")
    await greeter.run("publish_tweet", tweet="Having a great time with Pancaik! 🥞")


if __name__ == "__main__":
    asyncio.run(main())
