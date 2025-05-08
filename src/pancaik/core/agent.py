import inspect
from typing import Any, Dict
from datetime import datetime, timezone


from ..tools.base import _GLOBAL_TOOLS
from .config import logger


class Agent:
    """Base Agent class"""
    def __init__(self, id: str | dict, config: Dict[str, Any]):
        """Initialize the agent with configuration.

        Args:
            id: Unique identifier for this agent instance. Can be a string or MongoDB ObjectId dict.
            config: Configuration dictionary for the agent.

        Raises:
            ValueError: If no configuration is provided or invalid id format.
        """
        # Handle MongoDB ObjectId format
        if isinstance(id, dict) and "$oid" in id:
            self.id = id["$oid"]
        else:
            # Precondition: id must be a string if not MongoDB format
            assert isinstance(id, str), "Agent id must be a string or MongoDB ObjectId format"
            self.id = id

        # Precondition: config must be a dictionary
        assert isinstance(config, dict), "Config must be a dictionary"

        self.config = {}
        self.data_store: Dict[str, Any] = {}  # Add state store

        # Load configuration and ensure datetime values are UTC-aware
        self.config = self._ensure_utc_datetimes(config.copy())
        logger.info(f"Loaded configuration from provided dictionary for agent {self.id}")

    def _ensure_utc_datetimes(self, data: Any) -> Any:
        """Recursively ensure all datetime values in the data structure are UTC-aware.
        
        Args:
            data: Any data structure that might contain datetime objects
            
        Returns:
            The data structure with all datetime objects converted to UTC-aware
        """
        if isinstance(data, datetime):
            # Convert naive datetime to UTC
            if data.tzinfo is None:
                return data.replace(tzinfo=timezone.utc)
            return data
        elif isinstance(data, dict):
            return {k: self._ensure_utc_datetimes(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._ensure_utc_datetimes(item) for item in data]
        elif isinstance(data, tuple):
            return tuple(self._ensure_utc_datetimes(item) for item in data)
        return data

    @property
    def retry_count(self) -> int:
        """Get the current retry count for this agent."""
        return self.config.get("retry_count", 0)

    @property
    def retry_policy(self) -> Dict[str, Any] | bool:
        """Get the retry policy for this agent.
        
        Returns:
            Dict with retry configuration or False if retries are disabled
        """
        policy = self.config.get("retry_policy")
        if policy is None:
            # Default retry policy
            return {"minutes": 10, "max_retries": 5}
        return policy

    async def run_tool(self, tool_id: str | dict, **kwargs):
        """
        Run a tool with the given tool_id and kwargs. The tool_id can be either:
        1. A string identifying the tool to run
        2. A pipeline step configuration dictionary with 'id' and 'params' fields

        Args:
            tool_id: String ID of the tool to run or pipeline step configuration dict
            **kwargs: Parameters to pass to the tool

        Returns:
            Result of the tool execution
        """
        # Handle pipeline step configuration
        if isinstance(tool_id, dict):
            step = tool_id
            assert "id" in step, f"Pipeline step must have an 'id' field: {step}"
            assert "params" in step, f"Pipeline step must have a 'params' field: {step}"
            assert isinstance(step["params"], dict), f"Step params must be a dictionary: {step}"
            
            # Merge step params with existing kwargs, step params take precedence
            kwargs = {**kwargs, **step["params"]}
            tool_id = step["id"]

        # Validate tool_id is a string at this point
        assert isinstance(tool_id, str), "tool_id must be a string"
        assert tool_id in _GLOBAL_TOOLS, f"Tool '{tool_id}' not found in registered tools"

        # Get the tool method
        method = _GLOBAL_TOOLS[tool_id]
        
        # Get parameters from state
        sig = inspect.signature(method)
        params = {}

        # Add data_store parameter if the method accepts it
        if "data_store" in sig.parameters:
            params["data_store"] = self.data_store

        # Handle required parameters
        required_params = [
            param_name for param_name, param in sig.parameters.items() 
            if param.default == param.empty and param_name != "data_store"
        ]

        for param in required_params:
            # Check direct state
            if param in kwargs:
                params[param] = kwargs[param]
            elif param in self.data_store:
                params[param] = self.data_store[param]
            else:
                # Check nested state
                name_state = self.data_store.get(tool_id, {})
                if param in name_state:
                    params[param] = name_state[param]
                else:
                    raise ValueError(f"Required parameter '{param}' not found for tool {tool_id}")

        # Handle optional parameters
        optional_params = [
            param for param in sig.parameters.keys() 
            if param not in required_params and param != "data_store"
        ]

        for param in optional_params:
            if param in kwargs:
                params[param] = kwargs[param]
            elif param in self.data_store:
                params[param] = self.data_store[param]
            elif param in self.data_store.get(tool_id, {}):
                params[param] = self.data_store[tool_id][param]

        # Execute the tool
        result = await method(**params)

        # Update data store with the result
        if isinstance(result, dict):
            if "values" in result and isinstance(result["values"], dict):
                for key, value in result["values"].items():
                    self.data_store[key] = value
                assert all(k in self.data_store for k in result["values"].keys()), "All values must be added to data_store"
        else:
            self.data_store[tool_id] = result

        return result

    async def run(self, **kwargs):
        """
        Execute the agent's pipeline in two phases:
        1. Execute tools from config.tools array
        2. Publish outputs from config.outputs array

        Args:
            **kwargs: Parameters to pass to the tools

        Returns:
            Result of the execution (data_store)
        """
        # Initialize/update data store
        self.data_store["config"] = self.config
        self.data_store["agent_id"] = self.id
        self.data_store.update(kwargs)

        # Validate data store initialization
        assert "config" in self.data_store and "agent_id" in self.data_store, "Data store must contain config and agent_id"

        # 1. Execute tools pipeline
        tools_pipeline = self.config.get("tools", [])
        if tools_pipeline:
            assert isinstance(tools_pipeline, list), "Pipeline from config.tools must be a list"
            for step in tools_pipeline:
                logger.info(f"Agent {self.id}: Starting execution of step '{step['id']}'")
                result = await self.run_tool(step, **kwargs)
                logger.info(f"Agent {self.id}: Completed execution of step '{step['id']}'")
                if isinstance(result, dict) and result.get("should_exit", False):
                    logger.info(f"Agent {self.id}: Exiting pipeline early due to should_exit flag from step '{step['id']}'")
                    break

        # 2. Process outputs
        outputs_pipeline = self.config.get("outputs", [])
        if outputs_pipeline:
            assert isinstance(outputs_pipeline, list), "Pipeline from config.outputs must be a list"
            for output in outputs_pipeline:
                logger.info(f"Agent {self.id}: Starting execution of output step '{output['id']}'")
                await self.run_tool(output, **kwargs)
                logger.info(f"Agent {self.id}: Completed execution of output step '{output['id']}'")

        return self.data_store

    async def schedule_next_run(self, **kwargs):
        """
        Schedule the next run for the agent by processing the triggers array.
        This method is similar to run() but only processes trigger configurations.

        Args:
            **kwargs: Parameters to pass to the trigger tools

        Returns:
            Result of the trigger processing (data_store)
        """
        # Initialize/update data store
        self.data_store["config"] = self.config
        self.data_store["agent_id"] = self.id
        self.data_store.update(kwargs)

        # Validate data store initialization
        assert "config" in self.data_store and "agent_id" in self.data_store, "Data store must contain config and agent_id"

        # Process triggers pipeline
        triggers_pipeline = self.config.get("triggers", [])
        if triggers_pipeline:
            assert isinstance(triggers_pipeline, list), "Pipeline from config.triggers must be a list"
            for trigger in triggers_pipeline:
                logger.info(f"Agent {self.id}: Starting execution of trigger '{trigger['id']}'")
                result = await self.run_tool(trigger, **kwargs)
                logger.info(f"Agent {self.id}: Completed execution of trigger '{trigger['id']}'")
                if isinstance(result, dict) and result.get("should_exit", False):
                    logger.info(f"Agent {self.id}: Exiting triggers pipeline early due to should_exit flag from trigger '{trigger['id']}'")
                    break

        return self.data_store
        