import datetime
from datetime import timezone

from pancaik.core.agent import Agent


class GreetingAgent(Agent):
    """An agent specialized in greetings and conversations"""

    name = "greeting_agent"

    def __init__(self, id=None, yaml_path=None, use_default_config=True):
        super().__init__(yaml_path=yaml_path, id=id, use_default_config=use_default_config)

    async def say_current_hour(self):
        """Get and say the current time"""
        current_time = datetime.now(timezone.utc)
        formatted_time = current_time.strftime("%H:%M:%S")
        time_message = f"The current time is {formatted_time}."
        print(f"🕒 {time_message}")
        return {"values": {"time": time_message}}

    async def greet(self, name="World"):
        """Greet a person by name"""
        greeting = f"Hello, {name}! Nice to meet you."
        print(f"👋 {greeting}")
        return {"values": {"greeting": greeting, "tweet": greeting}}

    async def publish_tweet(self, tweet):
        """Simulate publishing a tweet (just returns the tweet text)"""
        print(f"🐦 Tweet published: {tweet}")
        return {"values": {"tweet": tweet}}
