"""
Twitter Agent for interacting with Twitter/X platform.

This agent is responsible for executing Twitter-related routines and tasks
rather than directly exposing Twitter API functionality.
"""

from ..core.agent import Agent
from ..core.config import logger


class TwitterAgent(Agent):
    """Twitter Agent for automated Twitter interaction routines and tasks."""

    def __init__(self, id=None, yaml_path=None, use_default_config=False):
        """Initialize the Twitter agent.

        Args:
            id: Optional agent ID
            yaml_path: Optional path to YAML configuration file
            use_default_config: Whether to use default configuration
        """
        super().__init__(yaml_path=yaml_path, id=id, use_default_config=use_default_config)

        # Validate that Twitter credentials are provided
        assert self.config.get("twitter", {}).get("credentials"), "Twitter credentials must be provided in configuration"

        logger.info(f"{self.id}: Initialized successfully")
