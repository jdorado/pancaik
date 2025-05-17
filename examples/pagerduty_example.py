"""Example usage of the PagerDuty utility."""
import asyncio
from pancaik import init
from core.utils.pagerduty import send_alert
import os

async def main():
    # Initialize pancaik with PagerDuty configuration
    config = {
        "db_connection": "mongodb://localhost:27017",
        "pagerduty_key": os.getenv("PAGERDUTY_KEY"),  # Optional: if not set, alerts will be skipped
        "pagerduty_inactive": False  # Optional: set to True to disable alerts
    }
    
    await init(config)
    
    # Example alert with details
    details = {
        "error_type": "DatabaseConnectionError",
        "message": "Failed to connect to database",
        "connection_string": "mongodb://localhost:27017",
        "environment": "production"
    }
    
    # Send initial alert
    dedup_key = "db_connection_1"
    success = await send_alert(
        event="Database Connection Failed",
        dedup_key=dedup_key,
        details=details,
        severity="error"
    )
    print(f"Alert sent successfully: {success}")
    
    # Later, when the issue is resolved
    success = await send_alert(
        event="Database Connection Failed",
        dedup_key=dedup_key,
        is_resolve=True,
        details={"resolution": "Connection restored"}
    )
    print(f"Alert resolved successfully: {success}")

if __name__ == "__main__":
    asyncio.run(main()) 