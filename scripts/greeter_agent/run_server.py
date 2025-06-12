from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, FastAPI
from greeter_agent import GreetingAgent

from pancaik import init
from pancaik.core import TaskHandler
from pancaik.core.config import get_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n=== Starting Greeter Agent Demo ===\n")

    # Initialize pancaik with configuration
    await init(
        {
            "db_connection": "mongodb://localhost:27017/pancaik",  # Replace with your DB connection
            "run_continuous": True,  # Set to True if you want continuous task running
            "app_title": "Greeter Agent Demo",
            "sleep_interval": 5,  # Run tasks every 5 seconds
            "task_limit": 10,  # Process up to 10 tasks per run
        }
    )

    # Clear all existing tasks from the database
    tasks_cleared = await TaskHandler.clear_all_tasks()
    print(f"Cleared {tasks_cleared} tasks from the database")

    # Initialize agent and schedule initial task
    greeter = GreetingAgent()

    # Schedule tasks with different delays
    now = datetime.now(timezone.utc)
    await greeter.schedule_task(task_name="greet_and_tweet", next_run=now, params={"name": "Alice"})
    await greeter.schedule_task(task_name="greet_share_time", next_run=now + timedelta(seconds=2), params={"name": "Bob"})
    await greeter.schedule_task(task_name="welcome_sequence", next_run=now + timedelta(seconds=4), params={"name": "Charlie"})

    yield

    # Cleanup on shutdown
    db = get_config("db")
    if db is not None:
        db.client.close()


app = FastAPI(lifespan=lifespan)
router = APIRouter()


@router.get("/hello")
async def hello_world():
    return {"message": "Hello, World!"}


@router.get("/greet/{name}")
async def greet_person(name: str):
    greeter = GreetingAgent()
    task_id = await greeter.schedule_task(task_name="greet_share_time", next_run=datetime.now(timezone.utc), params={"name": name})
    return {"task_id": task_id, "message": f"Scheduled greeting for {name}"}


app.include_router(router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("run_server:app", host="0.0.0.0", port=8080, reload=True)
