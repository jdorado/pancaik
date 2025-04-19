# Tasks

Tasks are central to the Pancaik Agents platform. They represent regular jobs that are scheduled to achieve specific objectives, which can be one-off tasks or recurring jobs.

## Task Types

### One-off Tasks
One-time tasks that execute once and then complete. These are useful for:
- Data migration jobs
- Setup procedures
- Cleanup operations
- One-time data processing

### Recurring Tasks
Jobs that run on a schedule, performing the same operation repeatedly. Examples include:
- Daily social media posts
- Hourly data synchronization
- Weekly report generation
- Monthly analytics processing

## Task Configuration

Tasks are configured using a simple declarative syntax in YAML:

```yaml
tasks:
  daily_twitter_post:
    objective: "Posts a daily thought to Twitter"
    scheduler:
      type: "cron"
      params:
        expression: "0 9 * * *"  # Runs at 9 AM daily
    pipeline:
      - generate_content
      - publish_to_twitter
    params:
      content_source: "thoughts_database"
      hashtags: ["dailythought", "pancaikagent"]
```

## Scheduler System

The Pancaik Agents platform includes a robust scheduler that supports multiple scheduling types:

### Cron-style Scheduling
For recurring tasks based on precise time patterns:

```yaml
scheduler:
  type: "cron"
  params:
    expression: "*/15 * * * *"  # Every 15 minutes
```

### Random Interval Scheduling
For tasks that should run at random times within specified ranges:

```yaml
scheduler:
  type: "random_interval"
  params:
    min_minutes: 5
    max_minutes: 30  # Random time between 5-30 minutes
```

### One-time Scheduling
For tasks that should run exactly once at a specific time:

```yaml
scheduler:
  type: "one_time"
  params:
    scheduled_time: "2023-10-15T14:30:00"  # Specific date and time
```

## Retry Policy

When a task fails, the system can automatically retry it based on a configurable retry policy. This allows you to specify how and when to retry failed tasks.

### Default Behavior
By default, failed tasks will be retried after 10 minutes.

### Configuring Retry Policies

You can configure retry policies in your task definitions:

```yaml
tasks:
  data_sync:
    objective: "Synchronize data from external API"
    scheduler:
      type: "cron"
      params:
        expression: "0 */2 * * *"  # Every 2 hours
    retry_policy:
      minutes: 30  # Retry after 30 minutes on failure
    pipeline:
      - fetch_data
      - process_data
      - save_to_database
```

### Disabling Retries

To disable retries for a specific task, set the retry_policy to `false`:

```yaml
tasks:
  critical_process:
    objective: "Run critical process that should not be retried"
    scheduler:
      type: "cron"
      params:
        expression: "0 0 * * *"  # Daily at midnight
    retry_policy: false  # No retries on failure
    pipeline:
      - run_critical_process
```

## Task Pipeline

Each task defines a pipeline of steps to execute in sequence:

```yaml
pipeline:
  - step_one
  - step_two
  - step_three
```

Each step in the pipeline corresponds to:
- A method in the agent class
- A registered tool
- Another task

## Task Lifecycle

1. **Definition**: Tasks are defined in the agent's configuration YAML
2. **Initialization**: 
   - The agent's `init_tasks()` method checks for existing tasks in the database
   - It only schedules tasks from the config that aren't already scheduled
   - Returns a dictionary mapping task names to their IDs
3. **Scheduling**: 
   - The `schedule_task()` method handles task scheduling
   - If no execution time is provided, it calculates the next run time based on scheduler configuration:
     - For `random_interval`: Selects a random time between min_minutes and max_minutes
     - For `cron`: Uses croniter to calculate the next run based on the cron expression
     - For `one_time`: Uses the provided scheduled_time
   - It registers the task with the TaskHandler system
4. **Execution**: When the task's time arrives, the system invokes the agent with the task
5. **Pipeline Processing**: 
   - The agent executes each step in the task's pipeline using the `run()` method
   - Results from each step are stored in the agent's data_store
6. **Completion**: Results are recorded and any follow-up actions are triggered
7. **Task Management**:
   - Tasks can be manually scheduled using `schedule_task()`
   - Existing tasks can be cleared using `clear_tasks()`

## Practical Examples

### Creating and Initializing an Agent with Tasks

```python
import asyncio
from pancaik.core.agent import Agent

# Create agent from YAML config file
async def setup_twitter_agent():
    # Create agent instance - will automatically load the YAML config
    twitter_agent = Agent(yaml_path="agents/TwitterAgent.yaml", id="twitter_bot_1")
    
    # Initialize all tasks from the config
    task_ids = await twitter_agent.init_tasks()
    print(f"Initialized tasks: {task_ids}")
    
    return twitter_agent

# Manual task scheduling
async def schedule_custom_tweet(agent: Agent, tweet_content: str):
    # Schedule a one-time task to post specific content
    task_id = await agent.schedule_task(
        task_name="post_single_tweet",
        next_run=None,  # Will use the scheduler config from YAML
        params={
            "content": tweet_content,
            "hashtags": ["custom", "pancaikagent"]
        }
    )
    print(f"Scheduled custom tweet with task_id: {task_id}")
    
# Usage
async def main():
    agent = await setup_twitter_agent()
    
    # Schedule a custom task
    await schedule_custom_tweet(
        agent, 
        "Check out our new Pancaik Agents platform!"
    )
    
    # Clear specific tasks if needed
    cleared_count = await agent.clear_tasks(["daily_twitter_post"])
    print(f"Cleared {cleared_count} tasks")

if __name__ == "__main__":
    asyncio.run(main())
```

### Example Task Execution Flow

When a task is executed, the system performs these operations:

```python
# Pseudocode of the internal execution flow
async def execute_task(agent_id, task_name, params):
    # 1. Load the agent
    agent = Agent.from_config({"id": agent_id, "class": "path.to.AgentClass"})
    
    # 2. Run the task - this executes the pipeline steps in sequence
    results = await agent.run(task_name, **params)
    
    # 3. For recurring tasks, reschedule the next run
    task_config = agent.tasks[task_name]
    if is_recurring_task(task_config):
        await agent.schedule_task(task_name)
        
    return results
``` 