# Server and Task Execution

The Pancaik Agents framework includes a built-in server that manages task execution and provides HTTP endpoints for interacting with your agents.

## How the Server Works

The server component of Pancaik Agents handles:

1. Task scheduling and execution
2. API endpoints for task management
3. Custom endpoints for your application

The server setup is simple and uses FastAPI's lifespan for proper initialization and cleanup:

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager
from pancaik import init

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize pancaik with configuration
    await init({
        "db_connection": "mongodb://localhost:27017/pancaik",  # Optional DB connection
        "run_continuous": True,  # Set to True for continuous task running
        "app_title": "Your Application Title",
        "sleep_interval": 5,  # Run tasks every 5 seconds
        "task_limit": 10  # Process up to 10 tasks per run
    })
    
    yield
    
    # Cleanup on shutdown
    db = get_config("db")
    if db is not None:
        db.client.close()

app = FastAPI(lifespan=lifespan)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
```

## Task Execution Flow

1. Tasks are scheduled with their next run time
2. The server continuously checks for tasks that are due to run based on the configured `sleep_interval`
3. When a task's scheduled time arrives, the server executes the corresponding agent method
4. The server processes up to `task_limit` tasks per run

Example of scheduling tasks:

```python
# Initialize agent and schedule tasks
greeter = GreetingAgent()
now = datetime.now()

# Schedule multiple tasks with different delays
await greeter.schedule_task(task_name="greet_and_tweet", next_run=now, params={"name": "Alice"})
await greeter.schedule_task(
    task_name="greet_share_time", 
    next_run=now + timedelta(seconds=2), 
    params={"name": "Bob"}
)
```

## Adding Custom Endpoints

You can extend the server with custom endpoints using FastAPI's router. Here's how to add endpoints:

```python
from fastapi import FastAPI, APIRouter

# Create a router for custom endpoints
router = APIRouter()

@router.get("/hello")
async def hello_world():
    return {"message": "Hello, World!"}

@router.get("/greet/{name}")
async def greet_person(name: str):
    greeter = GreetingAgent()
    task_id = await greeter.schedule_task(
        task_name="greet_share_time",
        next_run=datetime.now(),
        params={"name": name}
    )
    return {"task_id": task_id, "message": f"Scheduled greeting for {name}"}

# Include the router in the app
app.include_router(router)
```

After starting your server, you can access your endpoints:
- `http://localhost:8080/hello` returns: `{"message": "Hello, World!"}`
- `http://localhost:8080/greet/Alice` schedules a greeting task for Alice

The server supports both synchronous and asynchronous endpoint handlers, and you can organize your routes using FastAPI's powerful routing system. 