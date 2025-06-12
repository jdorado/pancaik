import inspect
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from bson import ObjectId

from ..tools.base import _GLOBAL_TOOLS
from ..utils.pagerduty import send_alert
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
        config["ai_models"] = {
            "default": "google/gemini-2.5-flash-preview-05-20",
            "composing": "anthropic/claude-3.5-haiku",
            "research": "perplexity/llama-3.1-sonar-large-128k-online",
            "research-mini": "x-ai/grok-3-mini-beta",
            "analyzing": "openai/o3-mini-high",
        }
        self.config = self._ensure_utc_datetimes(config.copy())

        # Initialize data stores - using lowercase with metadata
        self.data_store: Dict[str, Any] = {
            "config": config,
            "agent_id": self.id,
            "context": {},  # Context with metadata
            "outputs": {},  # Outputs with metadata
        }

        logger.info(f"Loaded configuration from provided dictionary for agent {self.id}")

    def _flatten_metadata_dict(self, metadata_dict: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Convert metadata dictionary to flattened values dictionary.

        Args:
            metadata_dict: Dictionary with metadata structure {key: {"value": val, ...}}

        Returns:
            Flattened dictionary {key: val}
        """
        return {k: v.get("value") for k, v in metadata_dict.items()}

    def _add_metadata(self, key: str, value: Any, metadata_dict: Dict[str, Dict[str, Any]], tool_id: str | dict, phase: str) -> None:
        """Add a value with metadata to the specified metadata dictionary.

        Args:
            key: Key for the value
            value: The value to store
            metadata_dict: Target metadata dictionary
            tool_id: ID of the tool that generated this value
            phase: Phase identifier (trigger, tool, or output)
        """
        assert phase in ["trigger", "tool", "output"], f"Invalid phase: {phase}"

        metadata_dict[key] = {
            "value": value,
            "tool_id": tool_id,
            "phase": phase,
            "created_at": datetime.now(timezone.utc),
        }

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

    async def run_tool(self, tool_id: str | dict, **kwargs):
        """Run a tool with the given tool_id and kwargs.

        Args:
            tool_id: String ID of the tool to run or pipeline step configuration dict
            **kwargs: Parameters to pass to the tool

        Returns:
            Result of the tool execution
        """
        # Get the current execution phase
        if kwargs.get("_is_trigger"):
            phase = "trigger"
            kwargs.pop("_is_trigger")
        elif kwargs.get("_is_output"):
            phase = "output"
            kwargs.pop("_is_output")
        else:
            phase = "tool"

        # Remove any existing phase info to avoid confusion
        kwargs.pop("_phase", None)

        # Handle pipeline step configuration
        if isinstance(tool_id, dict):
            step = tool_id
            assert "id" in step, f"Pipeline step must have an 'id' field: {step}"
            assert "params" in step, f"Pipeline step must have a 'params' field: {step}"
            assert isinstance(step["params"], dict), f"Step params must be a dictionary: {step}"

            # Merge step params with existing kwargs, step params take precedence
            kwargs = {**kwargs, **step["params"]}
            tool_id = step["id"]

        # Execute the tool and store results
        result = await self._execute_tool(tool_id, phase, **kwargs)
        return result

    async def _execute_tool(self, tool_id: str, phase: str, **kwargs):
        """Execute a tool and process its results.

        Args:
            tool_id: String ID of the tool to run
            phase: Current execution phase
            **kwargs: Tool parameters

        Returns:
            Tool execution result
        """
        # Validate tool_id is a string
        assert isinstance(tool_id, str), "tool_id must be a string"
        assert tool_id in _GLOBAL_TOOLS, f"Tool '{tool_id}' not found in registered tools"

        # Get the tool method
        method = _GLOBAL_TOOLS[tool_id]

        # Get parameters from state
        sig = inspect.signature(method)
        params = {}

        # Add data_store parameter if the method accepts it
        if "data_store" in sig.parameters:
            # Create flattened version of data store for tool
            flattened_data_store = self.data_store.copy()
            flattened_data_store["context"] = self._flatten_metadata_dict(self.data_store["context"]).copy()
            flattened_data_store["outputs"] = self._flatten_metadata_dict(self.data_store["outputs"]).copy()
            params["data_store"] = flattened_data_store

        # Get all parameters except data_store
        all_params = [param for param in sig.parameters.keys() if param != "data_store"]
        required_params = [
            param_name for param_name, param in sig.parameters.items() if param.default == param.empty and param_name != "data_store"
        ]

        # Handle all parameters in a single pass
        for param in all_params:
            # Check kwargs first - highest precedence
            if param in kwargs:
                params[param] = kwargs[param]
            # Then check outputs
            elif param in self.data_store["outputs"]:
                params[param] = self.data_store["outputs"][param].get("value")
            # Then check context
            elif param in self.data_store["context"]:
                params[param] = self.data_store["context"][param].get("value")
            # Finally check data_store root
            elif param in self.data_store:
                params[param] = self.data_store[param]
            elif param in required_params:
                # Postcondition: required parameters must be found
                assert False, f"Required parameter '{param}' not found in kwargs, outputs, or context for tool {tool_id}"

            # Remove from flattened context if exists to avoid duplication
            if "data_store" in params and param in params["data_store"]["context"]:
                del params["data_store"]["context"][param]

        # Execute the tool
        result = await method(**params)
        assert isinstance(result, dict), "Tool must return a dictionary"

        # Store tool results with proper phase tracking
        if "values" in result and isinstance(result["values"], dict):
            values = result["values"]

            # Handle delete_context if present in values
            if "delete_context" in values:
                delete_keys = values["delete_context"]
                # Convert single key to list for uniform handling
                if isinstance(delete_keys, str):
                    delete_keys = [delete_keys]
                # Delete each key from context if it exists
                if isinstance(delete_keys, list):
                    for key in delete_keys:
                        if key in self.data_store["context"]:
                            del self.data_store["context"][key]
                            logger.info(f"Agent {self.id}: Deleted key '{key}' from context")

            # Handle context values
            if "context" in values and isinstance(values["context"], dict):
                self._store_values_with_metadata(values["context"], self.data_store["context"], tool_id, phase)

            # Handle output values
            if "output" in values and isinstance(values["output"], dict):
                self._store_values_with_metadata(values["output"], self.data_store["outputs"], tool_id, phase)

            # Handle any other values
            for key, value in values.items():
                if key not in ["context", "output"]:
                    self.data_store[key] = value

            # Validate all values were properly stored
            for key in result["values"].keys():
                if key == "context":
                    assert all(
                        k in self.data_store["context"] for k in result["values"]["context"].keys()
                    ), "All context values must be added to data_store['context']"
                elif key == "output":
                    assert all(
                        k in self.data_store["outputs"] for k in result["values"]["output"].keys()
                    ), "All output values must be added to data_store['outputs']"
                else:
                    assert key in self.data_store, f"Value '{key}' must be added to data_store"

        return result

    async def run(self, simulate: bool = False, **kwargs):
        """Execute the agent's pipeline in two phases:
        1. Execute tools from config.tools array
        2. Publish outputs from config.outputs array

        Args:
            simulate: If True, don't process outputs
            **kwargs: Parameters to pass to the tools

        Returns:
            Result of the execution (data_store)
        """
        # Check if this is a resumed execution
        resume_from_step = kwargs.get("resume_from_step", 0)

        # Initialize/update data store - preserve existing state if resuming
        if resume_from_step > 0:
            # Only update with new kwargs, preserving existing context/outputs
            logger.info(f"Agent {self.id}: Preserving existing state while resuming from step {resume_from_step}")
            # Don't override context and outputs that were restored
            preserved_context = self.data_store.get("context", {})
            preserved_outputs = self.data_store.get("outputs", {})

            self.data_store.update(kwargs)

            # Restore preserved state
            if preserved_context:
                self.data_store["context"] = preserved_context
            if preserved_outputs:
                self.data_store["outputs"] = preserved_outputs
        else:
            # Normal initialization for new executions
            self.data_store.update(kwargs)

        # Validate data store initialization
        assert "config" in self.data_store and "agent_id" in self.data_store, "Data store must contain config and agent_id"

        # 1. Execute tools pipeline
        tools_pipeline = self.config.get("tools", [])
        if tools_pipeline:
            assert isinstance(tools_pipeline, list), "Pipeline from config.tools must be a list"

            # Start from the specified step index (0-based)
            for step_index, step in enumerate(tools_pipeline):
                # Skip steps if we're resuming from a later step
                if step_index < resume_from_step:
                    logger.info(f"Agent {self.id}: Skipping step {step_index} '{step['id']}' (resuming from step {resume_from_step})")
                    continue

                logger.info(f"Agent {self.id}: Starting execution of step {step_index} '{step['id']}'")

                # Pass resume info if this is the step we're resuming from
                step_kwargs = kwargs.copy()
                if step_index == resume_from_step:
                    step_kwargs["resuming_from_step"] = step["id"]
                    step_kwargs["is_resuming"] = True
                    logger.info(f"Agent {self.id}: Resuming step '{step['id']}' from processing mode")

                result = await self.run_tool(step, **step_kwargs)
                logger.info(f"Agent {self.id}: Completed execution of step {step_index} '{step['id']}'")

                # Check for processing flag
                if isinstance(result, dict) and result.get("should_process", False):
                    process_minutes = result.get("process_minutes", 10)  # Default 10 minutes
                    next_step = step_index  # Resume from current step

                    logger.info(
                        f"Agent {self.id}: Entering processing mode after step '{step['id']}' for {process_minutes} minutes. Will resume from step {next_step}"
                    )

                    # Schedule the resumption
                    await self._schedule_processing(process_minutes, next_step)

                    # Return early to enter processing mode
                    return {"processing": True, "resume_from_step": next_step, "process_minutes": process_minutes}

                # Check for exit flag (existing behavior)
                if isinstance(result, dict) and result.get("should_exit", False):
                    logger.warning(f"Agent {self.id}: Exiting pipeline early due to should_exit flag from step '{step['id']}'")
                    return self.data_store

        # If simulate is True, don't process outputs
        if simulate:
            return self.data_store

        # 2. Process outputs (only if we completed all tools or resumed past the tools phase)
        outputs_pipeline = self.config.get("outputs", [])
        if outputs_pipeline:
            assert isinstance(outputs_pipeline, list), "Pipeline from config.outputs must be a list"
            for output in outputs_pipeline:
                logger.info(f"Agent {self.id}: Starting execution of output step '{output['id']}'")
                # Execute output step with output phase
                await self.run_tool(output, _is_output=True, **kwargs)
                logger.info(f"Agent {self.id}: Completed execution of output step '{output['id']}'")

        # 3. Save outputs to database
        if self.data_store["outputs"]:
            # Filter outputs to only save those generated in the outputs phase
            outputs_to_save = {
                key: {
                    "agent_id": self.id,
                    "key": key,
                    "value": output_data["value"],
                    "tool_id": output_data["tool_id"],
                    "phase": output_data.get("phase", "unknown"),
                }
                for key, output_data in self.data_store["outputs"].items()
                if output_data.get("phase") == "output"
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

    async def _schedule_processing(self, process_minutes: int, resume_from_step: int):
        """
        Schedule the agent to resume execution after a processing period.
        Saves current context and outputs to be restored on resume.

        Args:
            process_minutes: Number of minutes to wait for processing
            resume_from_step: Step index to resume from (0-based)
        """
        from datetime import datetime, timedelta, timezone

        # Calculate the resume time
        current_time = datetime.now(timezone.utc)
        resume_time = current_time + timedelta(minutes=process_minutes)

        # Prepare processing state to save
        processing_state = {
            "context": self.data_store.get("context", {}),
            "outputs": self.data_store.get("outputs", {}),
        }

        # Update agent with processing information and state (keep status as "scheduled")
        await AgentHandler.update_agent_status(
            self.id,
            "scheduled",
            {
                "next_run": resume_time,
                "resume_from_step": resume_from_step,
                "processing_started_at": current_time,
                "process_minutes": process_minutes,
                "processing_state": processing_state,
                "error": None,
                "retry_count": 0,
            },
        )

        logger.info(f"Agent {self.id}: Scheduled to resume at {resume_time} from step {resume_from_step}")
        logger.info(
            f"Agent {self.id}: Saved processing state with {len(processing_state['context'])} context items and {len(processing_state['outputs'])} outputs"
        )

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
                # Only execute scheduler triggers - all others are handled separately
                if trigger.get("id") != "scheduler":
                    logger.info(f"Agent {self.id}: Skipping non-scheduler trigger '{trigger['id']}' in schedule_next_run")
                    continue

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

    def _store_values_with_metadata(
        self, values: Dict[str, Any], store_dict: Dict[str, Dict[str, Any]], tool_id: str | dict, phase: str = "unknown"
    ) -> None:
        """Store values in the specified store dictionary with metadata, handling key conflicts.

        Args:
            values: Dictionary of values to store {key: value}
            store_dict: Target store dictionary (context or outputs)
            tool_id: ID of the tool that generated these values
            phase: Optional phase identifier

        The method handles historical values by adding indexed postfixes:
        - Current value: key
        - Previous values: key_1, key_2, key_3, etc. (higher index = older value)
        """
        for key, value in values.items():
            base_key = key
            final_key = key

            # If key exists, shift all existing values with indexed postfixes
            if final_key in store_dict:
                # Find all existing keys with this base
                existing_keys = [
                    k for k in store_dict.keys() if k == base_key or (k.startswith(f"{base_key}_") and k[len(base_key) + 1 :].isdigit())
                ]

                # Sort by index (base key has no index, others are numbered)
                existing_keys.sort(key=lambda k: float("inf") if k == base_key else int(k[len(base_key) + 1 :]))

                # Shift all values to next index
                for old_key in reversed(existing_keys):
                    old_value = store_dict[old_key]
                    if old_key == base_key:
                        new_key = f"{base_key}_1"
                    else:
                        current_index = int(old_key[len(base_key) + 1 :])
                        new_key = f"{base_key}_{current_index + 1}"

                    # Store with original metadata
                    self._add_metadata(new_key, old_value["value"], store_dict, old_value["tool_id"], old_value.get("phase", "unknown"))

                    # Clean up old key if it's not the base key (which will be overwritten)
                    if old_key != base_key:
                        del store_dict[old_key]

            # Store new value with metadata
            self._add_metadata(final_key, value, store_dict, tool_id, phase)

        # Validate all values were stored
        assert all(k in store_dict for k in values.keys()), "All values must be added to store dictionary"

    def get_ordered_outputs(self) -> List[Dict[str, Any]]:
        """Get all outputs in order of creation.

        Returns:
            List of dictionaries containing the output value and its metadata, ordered by creation sequence
        """
        all_values = []
        store = self.data_store["outputs"]

        # Collect all output values with their metadata
        for key, metadata in store.items():
            value_info = {
                "key": key,
                "value": metadata["value"],
                "tool_id": metadata["tool_id"],
                "phase": metadata["phase"],
                "created_at": metadata["created_at"],
            }
            all_values.append(value_info)

        # Sort by creation timestamp
        all_values.sort(key=lambda x: x["created_at"])
        return all_values

    async def execute(self, no_retry: bool = False, **kwargs):
        """
        Execute a single agent's task with full lifecycle management including:
        - Status tracking (running, completed, failed)
        - Error handling and retry logic (unless no_retry=True)
        - Alert notifications
        - Scheduling next run (unless no_retry=True)
        - Processing mode and resumption handling

        Args:
            no_retry: If True, disables retry logic and scheduling for manual runs
            **kwargs: Parameters to pass to the agent execution

        Returns:
            Result of the execution (data_store) or None if failed permanently
        """
        from .ai_logger import ai_logger

        logger.info(f"Executing agent {self.id}")

        # Check if this agent is resuming from processing
        resume_from_step = self.config.get("resume_from_step", 0) or 0
        processing_state = self.config.get("processing_state")

        if resume_from_step > 0:
            logger.info(f"Agent {self.id}: Resuming execution from step {resume_from_step}")
            kwargs["resume_from_step"] = resume_from_step

            # Restore processing state if available
            if processing_state:
                logger.info(f"Agent {self.id}: Restoring processing state")

                # Restore context with metadata
                if "context" in processing_state and processing_state["context"]:
                    self.data_store["context"] = processing_state["context"]
                    logger.info(f"Agent {self.id}: Restored {len(processing_state['context'])} context items")

                # Restore outputs with metadata
                if "outputs" in processing_state and processing_state["outputs"]:
                    self.data_store["outputs"] = processing_state["outputs"]
                    logger.info(f"Agent {self.id}: Restored {len(processing_state['outputs'])} output items")



        # Mark agent as running
        await AgentHandler.update_agent_status(self.id, "running")

        try:
            # Run the agent
            result = await self.run(**kwargs)

            # Check if the agent is in processing mode
            if isinstance(result, dict) and result.get("processing", False):
                logger.info(f"Agent {self.id}: Execution in processing mode, will resume from step {result.get('resume_from_step')}")
                # Don't schedule next run or send alerts for processing agents
                return result

            # Update agent status with successful completion and last run time
            # Clear resume data only after successful completion
            current_time = datetime.now(timezone.utc)
            await AgentHandler.update_agent_status(
                self.id,
                "completed",
                {
                    "last_run": current_time,
                    "error": None,
                    "retry_count": 0,
                    "next_run": None,
                    "resume_from_step": None,  # Clear resume info after successful completion
                    "processing_state": None,  # Clear processing state after successful completion
                    "processing_started_at": None,  # Clear processing metadata
                    "process_minutes": None,
                },
            )

            # Schedule next run (unless this is a manual run)
            if not no_retry:
                await self.schedule_next_run(last_run=current_time)

                # Send resolution alert after scheduling
                await send_alert(
                    event=f"{self.id}: ({self.config['name']}) completed successfully", dedup_key=self.id, is_resolve=True, severity="info"
                )

            return result
        except Exception as e:
            error_message = f"{self.id}: {str(e)}"
            logger.error(error_message)

            retry_count = self.retry_count + 1
            current_time = datetime.now(timezone.utc)

            # Hardcoded retry policy values - exponential backoff
            base_retry_minutes = 10  # Start with 10 minutes
            max_retries = 10  # Maximum retry attempts

            # Calculate exponential backoff: base_minutes * (2 ^ (retry_count - 1))
            # Cap at 8 hours (480 minutes) to prevent extremely long delays
            retry_minutes = min(base_retry_minutes * (2 ** (retry_count - 1)), 480)

            # Invariant: retry parameters must be non-negative
            assert base_retry_minutes >= 0, "Base retry minutes must be a non-negative value"
            assert max_retries >= 0, "Max retries must be a non-negative value"

            # If no_retry is True, don't attempt retries - just fail and re-raise
            if no_retry:
                logger.info(f"Agent {self.id} failed during manual run (no_retry=True), not scheduling retry")
                await AgentHandler.update_agent_status(
                    self.id,
                    "failed",
                    {
                        "error": str(e),
                        "retry_count": 0,  # Reset retry count for manual runs
                        "next_run": None,
                    },
                )
                raise  # Re-raise the exception for the caller to handle

            # Check if we've reached the maximum number of retries
            if retry_count >= max_retries:
                logger.info(f"Agent {self.id} has reached maximum retry attempts ({max_retries}), not scheduling retry")
                await self.deactivate()  # In order to stop any sub-agents
                await AgentHandler.update_agent_status(
                    self.id,
                    "failed",
                    {
                        "error": str(e),
                        "retry_count": retry_count,
                        "next_run": None,
                        "is_active": False,
                    },
                )
                # Send critical alert for complete failure
                await send_alert(
                    event=f"{self.id}: ({self.config['name']}) failed permanently",
                    dedup_key=self.id,
                    details={"error": str(e), "retry_count": retry_count, "max_retries": max_retries},
                    severity="error",
                )
                return None

            # Schedule next run and update status with retry information
            await AgentHandler.update_agent_status(
                self.id,
                "scheduled",
                {"error": str(e), "retry_count": retry_count, "next_run": current_time + timedelta(minutes=retry_minutes)},
            )
            logger.info(f"Scheduled retry for agent {self.id} (attempt {retry_count}/{max_retries}) in {retry_minutes} minutes")
        finally:
            # Flush any buffered AI logs
            await ai_logger.flush()
