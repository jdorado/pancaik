import random
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Literal, Union

from ..core.agent_handler import AgentHandler
from ..core.config import logger
from .base import tool

# Define valid schedule types and interval units
ScheduleType = Literal['one-time', 'regular', 'random-interval']
IntervalUnit = Literal['minutes', 'hours', 'days', 'weeks', 'months']

def convert_to_datetime(timestamp: Union[str, int, float, datetime], param_name: str) -> datetime:
    """
    Convert various timestamp formats to datetime object in UTC.
    
    Args:
        timestamp: The timestamp to convert (string ISO format, Unix timestamp number, or datetime)
        param_name: Name of the parameter being converted (for error messages)
    
    Returns:
        datetime: The converted datetime object in UTC
        
    Raises:
        ValueError: If the timestamp is in an unsupported format
    """
    if isinstance(timestamp, str):
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        # Ensure timezone awareness
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    elif isinstance(timestamp, (int, float)):
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    elif isinstance(timestamp, datetime):
        # If datetime is naive, make it UTC
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=timezone.utc)
        return timestamp
    else:
        raise ValueError(f"{param_name} must be a string (ISO format), number (Unix timestamp), or datetime object")

@tool
async def scheduler(
    agent_id: str,
    scheduler_type: ScheduleType, 
    scheduler_params: Dict[str, Any],
    last_run: Optional[Union[str, int, float, datetime]] = None
) -> Dict[str, Any]:
    """
    Processes scheduling configuration from the UI and updates the agent's next_run timestamp.
    
    Args:
        agent_id: The ID of the agent to update
        scheduler_type: 'one-time' | 'regular' | 'random-interval'
        scheduler_params: OneTimeParams | RegularParams | RandomIntervalParams
            OneTimeParams: { timestamp: datetime }
            RegularParams: { 
                customInterval: { value: number, unit: IntervalUnit },
                startTime: datetime 
            }
            RandomIntervalParams: { minMinutes: number, maxMinutes: number }
        last_run: Optional timestamp of the last run (string ISO format, Unix timestamp, or datetime)

    Returns:
        Dictionary containing:
            success: bool - Whether the update was successful
            next_run: datetime - The calculated next run time (in UTC)
    """
    # Validate input parameters
    assert isinstance(agent_id, str), "agent_id must be a string"
    assert isinstance(scheduler_type, str), "scheduler_type must be a string"
    assert isinstance(scheduler_params, dict), "scheduler_params must be a dictionary"
    assert scheduler_type in ['one-time', 'regular', 'random-interval'], f"Invalid schedule type: {scheduler_type}"

    now = datetime.now(timezone.utc)
    next_run = None
    
    # Convert last_run to datetime if provided
    last_run_dt = convert_to_datetime(last_run, "last_run") if last_run is not None else None

    if scheduler_type == "one-time":
        assert "timestamp" in scheduler_params, "One-time schedule requires timestamp"
        
        # If this is a one-time schedule and it has already run, deactivate it
        if last_run_dt is not None:
            update_data = {
                "last_run": last_run_dt,
                "next_run": None,
                "status": None,
                "is_active": False,
                "updated_at": now,
                "retry_count": 0,
                "error": None
            }
            success = await AgentHandler.update_agent(agent_id, update_data)
            return {
                "success": success,
                "next_run": None
            }
            
        # If it hasn't run yet, schedule it
        next_run = convert_to_datetime(scheduler_params["timestamp"], "timestamp")

    elif scheduler_type == "regular":
        assert "customInterval" in scheduler_params, "Regular schedule requires interval configuration"
        assert "startTime" in scheduler_params, "Regular schedule requires start time"

        interval = scheduler_params["customInterval"]
        start_time = convert_to_datetime(scheduler_params["startTime"], "startTime")
        
        # Convert interval to minutes for internal use
        multipliers = {
            "minutes": 1,
            "hours": 60,
            "days": 1440,
            "weeks": 10080,
            "months": 43200  # Approximating month as 30 days
        }
        
        total_minutes = interval["value"] * multipliers[interval["unit"]]
        
        # If no previous run and start time is in future, use start time
        if last_run_dt is None and start_time > now:
            next_run = start_time
        else:
            # Use the most recent time between last_run and start_time
            reference_time = last_run_dt if last_run_dt is not None else start_time
            
            # Calculate next run based on interval from reference time
            elapsed_minutes = (now - reference_time).total_seconds() / 60
            intervals_passed = int(elapsed_minutes / total_minutes)
            
            # If we're exactly at an interval point, move to next interval
            if elapsed_minutes % total_minutes == 0:
                intervals_passed += 1
                
            next_run = reference_time + timedelta(minutes=total_minutes * intervals_passed)
            
            # Ensure next_run is in the future
            while next_run <= now:
                next_run += timedelta(minutes=total_minutes)

    elif scheduler_type == "random-interval":
        assert "minMinutes" in scheduler_params, "Random interval requires minimum minutes"
        assert "maxMinutes" in scheduler_params, "Random interval requires maximum minutes"

        min_minutes = scheduler_params["minMinutes"]
        max_minutes = scheduler_params["maxMinutes"]

        # Validate min/max values
        assert min_minutes > 0, "Minimum minutes must be positive"
        assert max_minutes >= min_minutes, "Maximum minutes must be greater than or equal to minimum"

        # Calculate next run time from last run or now
        reference_time = last_run_dt if last_run_dt is not None else now
        random_minutes = random.randint(min_minutes, max_minutes)
        next_run = reference_time + timedelta(minutes=random_minutes)
        
        # If next_run is in the past (could happen if last_run is old),
        # calculate from current time instead
        if next_run <= now:
            next_run = now + timedelta(minutes=random_minutes)

    else:
        raise ValueError(f"Unsupported schedule type: {scheduler_type}")

    # For non-one-time schedules that have a next_run, update with scheduled status
    if next_run is not None:
        assert next_run.tzinfo is not None, "next_run must be timezone-aware"
        assert next_run > now, "next_run must be in the future"
        
        # Update the agent's next_run time in the database
        logger.info(f"Updating agent {agent_id} with next_run {next_run}")
        success = await AgentHandler.update_agent(agent_id, {
            "next_run": next_run, 
            "last_run": last_run_dt,
            "status": "scheduled",
            "is_active": True,
            "updated_at": now,
            "retry_count": 0,
            "error": None
        })
    else:
        success = True  # For one-time tasks that were deactivated
    
    return {
        "success": success,
        "next_run": next_run
    }
