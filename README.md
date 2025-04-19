# Pancaik Agents

A framework for building intelligent agents that perform scheduled tasks and provide chat interfaces.

## Features

- **Task Automation**: Agents accomplish objectives through scheduled one-off or recurring tasks
- **Chat Interface**: Direct interaction with agents through conversational interfaces
- **Flexible Scheduling**: Support for cron-style, interval-based, and one-time scheduling
- **Extensible Architecture**: Easy to customize and extend for specific use cases

## Installation

```bash
# Install from PyPI
pip install pancaik
```

## Getting Started

Building a Pancaik agent involves three simple steps:

### 1. Define your agent's tasks in a YAML configuration

```yaml
# config.yaml
tasks:
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
```

### 2. Create your agent class with task functions

```python
# greeter_agent.py
from pancaik.core.agent import Agent
import datetime

class GreetingAgent(Agent):
    """An agent specialized in greetings and conversations"""
    name = "greeting_agent"
    
    def __init__(self, id=None, yaml_path=None):
        super().__init__(yaml_path=yaml_path, id=id)
    
    async def say_current_hour(self):
        """Get and say the current time"""
        current_time = datetime.datetime.now()
        formatted_time = current_time.strftime("%H:%M:%S")
        return {"time": f"The current time is {formatted_time}."}
        
    async def greet(self, name="World"):
        """Greet a person by name"""
        greeting = f"Hello, {name}! Nice to meet you."
        return {"greeting": greeting}
```

### 3. Run your agent

```python
# run_server.py
import asyncio
from greeter_agent import GreetingAgent
from pancaik import init, run_server
from datetime import datetime

async def main():
    # Initialize pancaik
    app = await init({
        "run_continuous": True,
        "app_title": "Greeter Agent Demo"
    })
    
    # Initialize agent
    greeter = GreetingAgent(yaml_path="config.yaml")

    # Run a task directly
    result = await greeter.run("greet", name="Alice")
    print(result["greeting"])  # Outputs: Hello, Alice! Nice to meet you.
    
    # Schedule a task
    await greeter.schedule_task(
        task_name="greet_share_time", 
        next_run=datetime.now(),
        params={"name": "Anna"}
    )

    return app

if __name__ == "__main__":
    app = asyncio.run(main())
    # Start the server
    run_server(app, host="0.0.0.0", port=8080)
```

## Use Cases

- Social media management with automated posting
- Customer support chatbots with knowledge base integration
- Inquiry and quotation systems with form processing
- Content aggregation and distribution systems

## Local Development

### Running MongoDB Locally

For local development and testing, you can use Docker Compose to run a MongoDB instance:

```bash
# Start MongoDB
docker-compose up -d

# Connect to the MongoDB instance
# Default connection string: mongodb://localhost:27017/pancaik

# Stop MongoDB when finished
docker-compose down
```

This will start a MongoDB container accessible at `mongodb://localhost:27017/pancaik`, which is the default connection string used by Pancaik.

## License

[MIT License](LICENSE)