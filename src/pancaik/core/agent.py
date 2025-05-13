import inspect
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from bson import ObjectId

from ..tools.base import _GLOBAL_TOOLS
from .agent_handler import AgentHandler
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

        # Load configuration and ensure datetime values are UTC-aware
        config["account_id"] = config.get("account_id", config.get("owner_id"))
        self.config = self._ensure_utc_datetimes(config.copy())

        # Initialize data stores - agent level uses uppercase, tool level uses lowercase
        self.data_store: Dict[str, Any] = {
            "config": config,
            "agent_id": self.id,
            "Context": {},  # Agent-level context with metadata
            "Outputs": {},  # Agent-level outputs with metadata
            "context": {},  # Tool-level simplified context
            "outputs": {},  # Tool-level simplified outputs
            "ai_models": {
                "default": "x-ai/grok-3-mini-beta",
                "composing": "anthropic/claude-3.7-sonnet",
                "research": "perplexity/llama-3.1-sonar-large-128k-online",
                "research-mini": "x-ai/grok-3-mini-beta",
                "analyzing": "o3-mini",
            },
        }

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
        # Extract phase from kwargs if present
        phase = kwargs.pop("_phase", "unknown")

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

        # Update tool-level context and outputs from agent-level storage
        for key, value_dict in self.data_store["Context"].items():
            if isinstance(value_dict, dict) and "value" in value_dict:
                self.data_store["context"][key] = value_dict["value"]

        for key, value_dict in self.data_store["Outputs"].items():
            if isinstance(value_dict, dict) and "value" in value_dict:
                self.data_store["outputs"][key] = value_dict["value"]

        # Add data_store parameter if the method accepts it
        if "data_store" in sig.parameters:
            params["data_store"] = self.data_store

        # Get all parameters except data_store
        all_params = [param for param in sig.parameters.keys() if param != "data_store"]
        required_params = [
            param_name for param_name, param in sig.parameters.items() if param.default == param.empty and param_name != "data_store"
        ]

        # Handle all parameters in a single pass
        for param in all_params:
            # Check sources in order of precedence
            if param in kwargs:
                params[param] = kwargs[param]
            elif param in self.data_store["outputs"]:
                params[param] = self.data_store["outputs"][param]
            elif param in self.data_store["context"]:
                params[param] = self.data_store["context"][param]
            elif param in self.data_store:
                params[param] = self.data_store[param]
            elif param in self.config:
                params[param] = self.config[param]
            elif param in required_params:
                # Postcondition: required parameters must be found
                assert False, f"Required parameter '{param}' not found in kwargs, outputs, or context for tool {tool_id}"

        # Execute the tool
        result = await method(**params)

        # Update data store with the result
        if isinstance(result, dict):
            if "values" in result and isinstance(result["values"], dict):
                values = result["values"]

                # Handle context values - auto-index if key exists
                if "context" in values and isinstance(values["context"], dict):
                    for key, value in values["context"].items():
                        base_key = key
                        final_key = key
                        counter = 1

                        # Auto-index if key exists
                        while final_key in self.data_store["Context"]:
                            counter += 1
                            final_key = f"{base_key}_{counter}"

                        # Store with metadata in agent-level Context
                        self.data_store["Context"][final_key] = {
                            "value": value,
                            "tool_id": tool_id,
                        }
                        # Update tool-level context
                        self.data_store["context"][final_key] = value

                # Handle output values
                if "output" in values and isinstance(values["output"], dict):
                    for key, value in values["output"].items():
                        # Store with metadata in agent-level Outputs
                        self.data_store["Outputs"][key] = {
                            "key": key,
                            "value": value,
                            "tool_id": tool_id,
                            "phase": phase,
                        }
                        # Update tool-level outputs
                        self.data_store["outputs"][key] = value

                # Handle any other values
                for key, value in values.items():
                    if key not in ["context", "output"]:
                        self.data_store[key] = value

                # Check that all values are properly stored
                for key in result["values"].keys():
                    if key == "context":
                        # Context values are stored in Context
                        assert all(
                            k in self.data_store["Context"] for k in result["values"]["context"].keys()
                        ), "All context values must be added to data_store['Context']"
                    elif key == "output":
                        # Output values are stored in Outputs
                        assert all(
                            k in self.data_store["Outputs"] for k in result["values"]["output"].keys()
                        ), "All output values must be added to data_store['Outputs']"
                    else:
                        # Other values are stored directly in data_store
                        assert key in self.data_store, f"Value '{key}' must be added to data_store"
        else:
            self.data_store[tool_id] = result

        return result

    async def run(self, simulate: bool = False, **kwargs):
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

        # If simulate is True, don't process outputs
        if simulate:
            return self.data_store

        # 2. Process outputs
        outputs_pipeline = self.config.get("outputs", [])
        if outputs_pipeline:
            assert isinstance(outputs_pipeline, list), "Pipeline from config.outputs must be a list"
            for output in outputs_pipeline:
                logger.info(f"Agent {self.id}: Starting execution of output step '{output['id']}'")
                # Pass outputs phase to run_tool
                await self.run_tool(output, _phase="outputs", **kwargs)
                logger.info(f"Agent {self.id}: Completed execution of output step '{output['id']}'")

        # 3. Save outputs to database
        if self.data_store["Outputs"]:
            # Filter outputs to only save those generated in the outputs phase
            outputs_to_save = {
                key: {
                    "agent_id": self.id,
                    "key": key,
                    "value": output_data["value"],
                    "tool_id": output_data["tool_id"],
                    "phase": output_data.get("phase", "unknown"),
                }
                for key, output_data in self.data_store["Outputs"].items()
                if output_data.get("phase") == "outputs"
            }

            if outputs_to_save:
                logger.info(f"Agent {self.id}: Saving {len(outputs_to_save)} outputs to database (outputs phase only)")
                try:
                    # Save outputs to database
                    saved = await AgentHandler.save_agent_outputs(self.id, outputs_to_save)
                    logger.info(f"Agent {self.id}: Successfully saved {saved} outputs to database")

                    # Validate outputs were saved
                    assert saved == len(outputs_to_save), f"Expected to save {len(outputs_to_save)} outputs, but saved {saved}"
                except Exception as e:
                    logger.error(f"Agent {self.id}: Failed to save outputs to database: {str(e)}")
            else:
                logger.info(f"Agent {self.id}: No outputs from outputs phase to save to database")

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

    async def _get_required_sub_agents(self) -> List[Tuple[str, str]]:
        """
        Get list of required sub-agents by inspecting tool signatures.

        Returns:
            List of tuples (step_id, required_agent)
        """
        requirements = []

        # Check tools pipeline only
        tools_pipeline = self.config.get("tools", [])
        for step in tools_pipeline:
            # Get step ID and tool ID
            step_id = step.get("instance_id") if isinstance(step, dict) else None
            tool_id = step["id"] if isinstance(step, dict) else step

            if not step_id:
                logger.warning(f"Step {tool_id} has no instance_id, skipping sub-agent check")
                continue

            tool = _GLOBAL_TOOLS.get(tool_id)
            if tool and hasattr(tool, "_required_agents"):
                for required_agent in tool._required_agents:
                    requirements.append((step_id, required_agent))

        return requirements

    async def activate(self, **kwargs):
        """
        Activate the agent by setting up required sub-agents.
        Always deletes and recreates the hierarchy to ensure latest parameters are propagated.
        If activation fails, ensures cleanup of any partially created hierarchy.
        """
        # Get all required sub-agents from tool signatures
        step_requirements = await self._get_required_sub_agents()
        created_agents = []  # Track created agents for cleanup in case of failure

        try:
            if step_requirements:
                # First delete any existing hierarchy to ensure clean state
                deleted = await AgentHandler.deactivate_agent_hierarchy(self.id)
                if deleted:
                    logger.info(f"Cleaned up {len(deleted)-1} existing sub-agents for agent {self.id}")

                # Create each required agent fresh
                for step_id, required_agent in step_requirements:
                    logger.info(f"Creating new sub-agent {required_agent} for step {step_id} (owner: {self.id})")
                    try:
                        sub_agent_id = await self.create_sub_agent(required_agent, step_id)
                        created_agents.append(sub_agent_id)
                        logger.info(f"Created and activated sub-agent with ID: {sub_agent_id}")
                    except Exception as e:
                        logger.error(f"Failed to create/activate sub-agent {required_agent} for step {step_id}: {str(e)}")
                        raise  # Re-raise to trigger cleanup

            # Schedule next run after activation
            await self.schedule_next_run()

        except Exception as e:
            # If anything fails during activation, clean up any created agents
            if created_agents:
                logger.warning(f"Activation failed, cleaning up {len(created_agents)} created sub-agents")
                try:
                    # Deactivate the entire hierarchy to ensure complete cleanup
                    await self.deactivate()
                except Exception as cleanup_error:
                    logger.error(f"Error during cleanup after failed activation: {str(cleanup_error)}")
                    # Don't raise cleanup error, we want to raise the original error

            # Re-raise the original error
            raise Exception(f"Failed to activate agent {self.id}: {str(e)}") from e

    async def deactivate(self, **kwargs):
        """
        Deactivate this agent and delete all its descendants.
        The agent itself is preserved but marked as inactive, while all its descendants are permanently deleted.
        """
        # Deactivate this agent and delete descendants
        affected = await AgentHandler.deactivate_agent_hierarchy(self.id)
        logger.info(f"Deactivated agent {self.id} and deleted {len(affected)-1} descendants")

    async def create_sub_agent(self, required_agent: str, step_id: str, override_config: Dict[str, Any] = None) -> str:
        """
        Create a new sub-agent instance.

        Args:
            required_agent: Name of the required agent configuration
            step_id: ID of the step requiring this agent
            override_config: Optional configuration overrides

        Returns:
            ID of the created agent
        """
        from .agent_registry import create_agent_instance, get_agent_config

        # Generate a new MongoDB ObjectId for the sub-agent
        sub_agent_id = str(ObjectId())

        # Get parent tool configuration to extract params
        parent_tool = next((tool for tool in self.config.get("tools", []) if tool.get("instance_id") == step_id), None)

        assert parent_tool is not None, f"No tool found with instance_id {step_id} in parent agent {self.id}"

        # Get account_id - either from our config or use our id if we're the root account holder
        account_id = self.config.get("account_id")
        assert account_id is not None, "Failed to determine account_id for sub-agent"

        # Create base config overrides with essential fields
        base_overrides = {
            "owner_id": self.id,  # This agent owns its sub-agents
            "step_id": step_id,
            "required_agent": required_agent,
            "account_id": account_id,  # Propagate account holder down the hierarchy
        }

        # Get the base configuration without instantiating an agent
        sub_agent_config = get_agent_config(required_agent)

        # Ensure each tool has an instance_id
        if "tools" in sub_agent_config:
            tools = sub_agent_config["tools"]
            for i, tool in enumerate(tools):
                if isinstance(tool, dict):
                    if not tool.get("instance_id"):
                        # Generate a unique instance_id if not provided
                        tool["instance_id"] = f"{sub_agent_id}_{i}"
                else:
                    # If tool is just a string (tool name), convert to dict with instance_id
                    tools[i] = {"id": tool, "instance_id": f"{sub_agent_id}_{i}"}
            base_overrides["tools"] = tools

        # Copy required params from parent tool to sub-agent config
        if parent_tool and "params" in parent_tool:
            sub_agent_tools = base_overrides.get("tools", [])

            # For each tool in sub-agent config
            for sub_tool in sub_agent_tools:
                if isinstance(sub_tool, dict) and "params" in sub_tool:
                    # Only copy parameters that exist in both configs
                    sub_tool["params"].update({k: v for k, v in parent_tool["params"].items() if k in sub_tool["params"]})

        # Merge with any additional overrides
        if override_config:
            base_overrides.update(override_config)

        # Create the final agent instance with all overrides
        agent = create_agent_instance(required_agent, sub_agent_id, base_overrides)

        # Save agent to database using owner_id for hierarchy
        success = await AgentHandler.insert_agent(sub_agent_id, agent.config, owner_id=self.id)
        if not success:
            raise Exception(f"Failed to create sub-agent {sub_agent_id}")

        # Activate the agent
        await agent.activate()

        return sub_agent_id
