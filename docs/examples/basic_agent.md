# Basic Agent Example

The Greeter Agent demonstrates the core functionality of Pancaik Agents, showing how to create a simple agent with multiple methods that can be orchestrated using a configuration file.

## Agent Implementation

```python
import datetime
from pancaik.core.agent import Agent

class GreetingAgent(Agent):
    """An agent specialized in greetings and conversations"""
    name = "greeting_agent"
    
    def __init__(self, id=None, yaml_path=None, use_default_config=True):
        super().__init__(yaml_path=yaml_path, id=id, use_default_config=use_default_config)
    
    async def say_current_hour(self):
        """Get and say the current time"""
        current_time = datetime.datetime.now()
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
```

This simple agent has three main methods:

1. `greet`: Generates a greeting message for a specified name and prints it with an emoji
2. `say_current_hour`: Returns the current time in a formatted message with a clock emoji
3. `publish_tweet`: Simulates publishing a tweet (demonstration purposes)

## Configuration

The agent is configured through a YAML file that defines tasks and their orchestration:

```yaml
tasks:
  greet_and_tweet:
    objective: "Greet a person by name"
    pipeline:
      - greet
      - publish_tweet
  greet_share_time:
    objective: "Greet a person by name and share the current time"
    scheduler:
      type: "random_interval"
      params:
        min_minutes: 5
        max_minutes: 30
    pipeline:
      - greet
      - say_current_hour
  welcome_sequence:
    objective: "Run a full welcome sequence for new users"
    pipeline:
      - greet_and_tweet
      - say_current_hour
```

## Running the Agent

There are two ways to run the agent:

### 1. Direct Script Execution

```python
import asyncio
from pathlib import Path
import sys

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
```

### 2. FastAPI Server Integration

You can also run the agent as part of a FastAPI server, which allows for HTTP-based interaction and scheduled task execution:

```python
from fastapi import FastAPI, APIRouter
from datetime import datetime, timedelta
from pancaik import init
from pancaik.core import TaskHandler
from pancaik.core.config import get_config

app = FastAPI()
router = APIRouter()

@router.get("/greet/{name}")
async def greet_person(name: str):
    greeter = GreetingAgent()
    task_id = await greeter.schedule_task(
        task_name="greet_share_time", 
        next_run=datetime.now(), 
        params={"name": name}
    )
    return {"task_id": task_id, "message": f"Scheduled greeting for {name}"}

# Initialize Pancaik with configuration
await init({
    "db_connection": "mongodb://localhost:27017/pancaik",
    "run_continuous": True,
    "app_title": "Greeter Agent Demo",
    "sleep_interval": 5,
    "task_limit": 10
})
```

## Key Features Demonstrated

This example demonstrates several key features of Pancaik Agents:

1. **Task Definition**: Define tasks in YAML configuration
2. **Method Orchestration**: Chain methods together in pipelines
3. **Scheduled Execution**: Schedule tasks with specific run times or intervals
4. **Return Values**: Return structured data with the `values` key
5. **Task Composition**: Combine tasks to create more complex workflows
6. **HTTP Integration**: Expose agent functionality via FastAPI endpoints
7. **Visual Feedback**: Use emojis and print statements for better visibility
8. **Database Integration**: MongoDB support for task persistence

The Greeter Agent serves as a great starting point for understanding the fundamental concepts of Pancaik Agents before moving on to more complex integrations. 