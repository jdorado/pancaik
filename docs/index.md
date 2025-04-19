# Pancaik Agents

Welcome to the Pancaik Agents documentation. This platform helps you create and manage autonomous agents that can perform scheduled tasks and provide interactive chat interfaces.

## Overview

Pancaik Agents is a framework for building intelligent agents that can:

- Perform scheduled tasks to accomplish specific objectives
- Provide a chat interface for direct interaction
- Execute both one-off tasks and regular jobs
- Handle complex workflows autonomously

## Features

- **Task Automation**: Agents accomplish objectives through scheduled one-off or recurring tasks
- **Chat Interface**: Direct interaction with agents through conversational interfaces
- **Flexible Scheduling**: Support for cron-style, interval-based, and one-time scheduling
- **Extensible Architecture**: Easy to customize and extend for specific use cases

## Installation

```bash
# Install from PyPI
pip install pancaik

# Or using Poetry
poetry install
```

## Getting Started

Building a Pancaik agent involves these simple steps:

### 1. Define your agent class with task functions

```python
# greeter_agent.py
from pancaik.core.agent import Agent

class GreetingAgent(Agent):
    """An agent specialized in greetings and conversations"""
    
    def __init__(self, id=None):
        super().__init__(id=id)
    
    async def greet(self, name="World"):
        """Greet a person by name"""
        greeting = f"Hello, {name}! Nice to meet you."
        return {"greeting": greeting}
        
    async def greet_share_time(self, name="World"):
        """Greet and share the current time"""
        # Implementation here
        pass
        
    async def publish_tweet(self, tweet: str):
        """Post a tweet"""
        # Implementation here
        pass
```

### 2. Run your agent directly

```python
# run_agent.py
import asyncio
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

### 3. Or create a server with scheduled tasks

```python
# run_server.py
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI, APIRouter
from greeter_agent import GreetingAgent
from pancaik import init
from pancaik.core import TaskHandler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize pancaik with configuration
    await init({
        "db_connection": "mongodb://localhost:27017/pancaik",
        "run_continuous": True,
        "app_title": "Greeter Agent Demo",
        "sleep_interval": 5,
        "task_limit": 10
    })

    # Initialize agent and schedule tasks
    greeter = GreetingAgent()
    now = datetime.now()
    
    # Schedule multiple tasks with different delays
    await greeter.schedule_task(
        task_name="greet_and_tweet", 
        next_run=now, 
        params={"name": "Alice"}
    )
    await greeter.schedule_task(
        task_name="greet_share_time", 
        next_run=now + timedelta(seconds=2), 
        params={"name": "Bob"}
    )
    
    yield

app = FastAPI(lifespan=lifespan)
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

app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("run_server:app", host="0.0.0.0", port=8080, reload=True)
```

## Use Cases

- Automated task scheduling and execution
- Interactive chatbots with custom business logic
- Workflow automation systems
- Data processing and monitoring agents

## Quick Navigation

- [Features](features.md) - Core capabilities of Pancaik Agents
- [Tasks](tasks.md) - How to set up and schedule agent tasks
- [Examples](examples.md) - Sample use cases and implementations

## License

[MIT License](https://github.com/jdorado/pancaik/blob/main/LICENSE)
