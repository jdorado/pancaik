"""
Twitter indexer agent configuration.
Defines the minimal required configuration for a twitter indexing agent.
"""

from typing import Any, Dict

CONFIG: Dict[str, Any] = {
    "tools": [
        {
            "id": "twitter_index_user",
            "instance_id": "",  # Will be populated by parent agent
            "params": {
                "twitter_connection": "",  # Required param from parent
                "target_handle": "",  # Required param from parent
            },
        }
    ],
    "triggers": [
        {
            "id": "scheduler",
            "instance_id": "",  # Will be populated when agent is created
            "params": {
                "scheduler_type": "regular",
                "scheduler_params": {"customInterval": {"value": 60 * 3, "unit": "minutes"}, "startTime": "2025-05-08T12:22:39.104Z"},
            },
        }
    ],
    "outputs": [],
}
