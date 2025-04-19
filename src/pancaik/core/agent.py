import importlib
import inspect
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import croniter
import yaml

from ..tools.base import _GLOBAL_TOOLS
from .config import logger
from .task_handler import TaskHandler


class Agent:
    """Base Agent class"""

    name = "base_agent"

    def __init__(self, yaml_path: Optional[str] = None, id: Optional[str] = None, use_default_config: bool = False):
        """Initialize the agent with configuration.

        This class supports three ways to load configuration:
        1. Use only the default configuration file in the agent's module directory
        2. Use only a user-provided configuration file
        3. Merge both default and user-provided configurations, with the user config taking precedence

        Args:
            yaml_path: Optional path to a YAML configuration file.
                      If None, the default config for the agent class will be used.
            id: Optional unique identifier for this agent instance.
                If None, the class name attribute will be used.
            use_default_config: When True and yaml_path is provided, both configurations
                               will be merged with yaml_path taking precedence. When False,
                               only yaml_path will be used if provided.

        Raises:
            ValueError: If no configuration file is found.
        """
        # Precondition: id must be a string if provided
        assert id is None or isinstance(id, str), "Agent id must be a string if provided"

        self.config = {}
        self.tasks = {}
        self.data_store: Dict[str, Any] = {}  # Add state store
        self.id = id or self.name  # Use provided ID or default to class name

        # Store yaml_path and use_default_config for task scheduling
        self.yaml_path = yaml_path
        self.use_default_config = use_default_config

        # Find default config file in the class's directory
        default_yaml_path = self._find_default_config()

        # Case 1: User provided a yaml_path and use_default_config is True (merge both configs)
        if yaml_path and use_default_config and default_yaml_path:
            # Precondition: yaml_path must be a string
            assert isinstance(yaml_path, str), "yaml_path must be a string"
            # Load default config first
            self.load_config_from_file(default_yaml_path)
            # Then overlay with user-provided config (takes precedence)
            self.load_config_from_file(yaml_path, merge=True)
            logger.info(f"Loaded merged configuration from {default_yaml_path} and {yaml_path}")

        # Case 2: User provided a yaml_path but use_default_config is False (use only user config)
        elif yaml_path:
            # Precondition: yaml_path must be a string
            assert isinstance(yaml_path, str), "yaml_path must be a string"
            self.load_config_from_file(yaml_path)
            logger.info(f"Loaded configuration from {yaml_path}")

        # Case 3: No yaml_path provided, use default config
        elif default_yaml_path:
            self.load_config_from_file(default_yaml_path)
            logger.info(f"Loaded default configuration from {default_yaml_path}")

        else:
            raise ValueError(f"No config file found for {self.__class__.__name__}")

        # Validate the function names in the class
        self._validate_names()

        # Postcondition: id must be set
        assert self.id, "Agent id must be set after initialization"
        # Postcondition: config must be a dictionary
        assert isinstance(self.config, dict), "Agent config must be a dictionary after initialization"

    async def schedule_task(
        self, task_name: str, next_run: Optional[datetime] = None, params: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Schedule a task to run at a specified time.

        Args:
            task_name: Name of the task to schedule
            next_run: Optional datetime when the task should run. If not provided,
                     it will use the scheduler configuration from the task.
                     If no scheduler is defined and no next_run is provided, the task will not be scheduled.
            params: Optional parameters to pass to the task

        Returns:
            task_id: The unique identifier for the scheduled task, or None if task was not scheduled
        """
        # Precondition: task_name must be a non-empty string
        assert isinstance(task_name, str) and task_name.strip(), "Task name must be a non-empty string"
        # Precondition: next_run must be a datetime object if provided
        assert next_run is None or isinstance(next_run, datetime), "next_run must be a datetime object if provided"
        # Precondition: params must be a dictionary if provided
        assert params is None or isinstance(params, dict), "params must be a dictionary if provided"
        # Precondition: Verify the task exists in the agent's tasks
        assert task_name in self.tasks, f"Task '{task_name}' not found in agent {self.id}"

        # Get the full agent class path
        agent_class = f"{self.__class__.__module__}.{self.__class__.__name__}"

        # If next_run is not provided, calculate it based on the task's scheduler config
        if next_run is None and task_name in self.tasks:
            task_config = self.tasks[task_name]
            scheduler_config = task_config.get("scheduler")

            if scheduler_config:
                # Precondition: scheduler_config must contain a type
                assert "type" in scheduler_config, f"Scheduler config for task {task_name} must contain a 'type'"

                scheduler_type = scheduler_config.get("type")
                scheduler_params = scheduler_config.get("params", {})

                if scheduler_type == "random_interval":
                    min_minutes = int(scheduler_params.get("min_minutes", 5))
                    max_minutes = int(scheduler_params.get("max_minutes", 60))
                    # Invariant: min_minutes must be less than or equal to max_minutes
                    assert min_minutes <= max_minutes, "Min minutes must be less than or equal to max minutes"
                    random_minutes = random.randint(min_minutes, max_minutes)
                    next_run = datetime.now() + timedelta(minutes=random_minutes)

                elif scheduler_type == "cron":
                    cron_expression = scheduler_params.get("expression")
                    # Precondition: cron expression must be provided
                    assert cron_expression, f"Cron expression not provided for task {task_name}"

                    # Use croniter to calculate the next run time
                    cron = croniter.croniter(cron_expression, datetime.now())
                    next_run = cron.get_next(datetime)

                elif scheduler_type == "one_time":
                    scheduled_time = scheduler_params.get("scheduled_time")
                    # Precondition: scheduled_time must be provided
                    assert scheduled_time, f"Scheduled time not provided for task {task_name}"
                    next_run = scheduled_time

                else:
                    raise ValueError(f"Unknown scheduler type: {scheduler_type}")

        # If no next_run time was provided or calculated, don't schedule the task
        if next_run is None:
            return None

        # Use the TaskHandler to create the task, passing yaml_path and use_default_config
        task_id = await TaskHandler.create_task(
            task_name=task_name,
            agent_id=self.id,
            agent_class=agent_class,
            next_run=next_run,
            params=params,
            yaml_path=self.yaml_path,
            use_default_config=self.use_default_config,
        )

        # Postcondition: task_id must be a string or None
        assert task_id is None or isinstance(task_id, str), "task_id must be a string or None"

        return task_id

    async def init_tasks(self) -> Dict[str, str]:
        """
        Initialize all tasks with schedulers that haven't been initialized yet.

        This checks the database for existing tasks and schedules any tasks
        from the config that are not already scheduled.

        Returns:
            Dict[str, str]: Dictionary mapping task names to their task_ids
        """
        # Precondition: self.id must be a non-empty string
        assert self.id and isinstance(self.id, str), "Agent id must be a non-empty string"
        # Precondition: self.tasks must be a dictionary
        assert isinstance(self.tasks, dict), "Agent tasks must be a dictionary"

        # Get all tasks for this agent
        agent_tasks = await TaskHandler.get_agent_tasks(self.id)
        # Postcondition: agent_tasks must be a list
        assert isinstance(agent_tasks, list), "agent_tasks must be a list"

        existing_task_names = {task["task_name"]: task["status"] for task in agent_tasks}

        # Dictionary to store task_ids
        task_ids = {}

        # Process all tasks from config
        for task_name, task_config in self.tasks.items():
            # Skip if already scheduled and status is 'scheduled'
            if task_name in existing_task_names and existing_task_names[task_name] == "scheduled":
                continue

            # Check if it has a scheduler
            if not task_config.get("scheduler"):
                continue

            # If task exists and status is not 'scheduled', log a warning
            if task_name in existing_task_names and existing_task_names[task_name] != "scheduled":
                logger.warning(f"Rescheduling task: {task_name} with status: {existing_task_names[task_name]}")

            # Schedule the task - next_run will be calculated in schedule_task if not provided
            task_id = await self.schedule_task(task_name=task_name, params=task_config.get("params", {}))

            if task_id:
                task_ids[task_name] = task_id

        # Postcondition: task_ids must be a dictionary
        assert isinstance(task_ids, dict), "task_ids must be a dictionary"
        # Invariant: All keys in task_ids must be valid task names
        assert all(name in self.tasks for name in task_ids.keys()), "All keys in task_ids must be valid task names"

        return task_ids

    async def clear_tasks(self, task_names: Optional[List[str]] = None) -> int:
        """
        Clear scheduled tasks for this agent.

        Args:
            task_names: Optional list of task names to clear.
                      If not provided, all tasks for this agent will be cleared.

        Returns:
            int: Number of tasks cleared
        """
        # Precondition: self.id must be a non-empty string
        assert self.id and isinstance(self.id, str), "Agent id must be a non-empty string"
        # Precondition: task_names must be a list of strings if provided
        assert task_names is None or (
            isinstance(task_names, list) and all(isinstance(name, str) for name in task_names)
        ), "task_names must be a list of strings if provided"

        # If task_names is provided, all must be valid task names
        if task_names:
            assert all(name in self.tasks for name in task_names), "All task names must be valid tasks in the agent"

        # Use the TaskHandler to delete agent tasks
        num_deleted = await TaskHandler.delete_agent_tasks(self.id, task_names)

        # Postcondition: num_deleted must be a non-negative integer
        assert isinstance(num_deleted, int) and num_deleted >= 0, "Number of deleted tasks must be a non-negative integer"

        return num_deleted

    def _find_default_config(self) -> Optional[str]:
        """
        Find the default config file for this agent class
        Looks for a YAML file in the same directory as the agent class with the same name
        """
        # Get the module and class name
        module = sys.modules[self.__class__.__module__]

        # If no module file is found, return None
        if not hasattr(module, "__file__"):
            return None

        # Get the directory of the module
        module_dir = Path(os.path.dirname(os.path.abspath(module.__file__)))

        # Invariant: module_dir must be a Path object and must exist
        assert isinstance(module_dir, Path) and module_dir.exists(), "Module directory must be a valid Path that exists"

        # Try class name first (e.g. GreetingAgent.yaml)
        config_file = module_dir / f"{self.__class__.__name__}.yaml"
        if config_file.exists():
            return str(config_file)

        # Try lowercase class name (e.g. greetingagent.yaml)
        config_file = module_dir / f"{self.__class__.__name__.lower()}.yaml"
        if config_file.exists():
            return str(config_file)

        # Try name attribute (e.g. greeting_agent.yaml)
        config_file = module_dir / f"{self.name}.yaml"
        if config_file.exists():
            return str(config_file)

        # Try config.yaml
        config_file = module_dir / "config.yaml"
        if config_file.exists():
            return str(config_file)

        # Postcondition: return None if no config file found
        return None

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "Agent":
        """
        Load an agent from a configuration dictionary

        Args:
            config: Dictionary with agent configuration
                Required keys:
                - 'class': Full path to the agent class (e.g. 'package.module.ClassName')
                - 'id': Unique identifier for the agent
                Optional keys:
                - 'yaml_path': Path to YAML config file (if not provided, will attempt to find it)
                - 'use_default_config': Whether to use default configuration (defaults to False)
                - Any other parameters to pass to the agent constructor

        Returns:
            Instantiated agent
        """
        # Precondition: config must be a dictionary
        assert isinstance(config, dict), "Config must be a dictionary"

        class_path = config.get("class")
        # Precondition: class_path must be a non-empty string
        assert class_path and isinstance(class_path, str), "Agent config must contain 'class' attribute as a non-empty string"

        # Precondition: id must be in config
        assert "id" in config, "Agent config must contain 'id' attribute"
        # Precondition: id must be a string
        assert isinstance(config["id"], str), "Agent id must be a string"

        # Extract module and class name
        # Precondition: class_path must contain at least one dot
        assert "." in class_path, "Class path must be in format 'package.module.ClassName'"
        module_path, class_name = class_path.rsplit(".", 1)

        # Import the module dynamically
        try:
            module = importlib.import_module(module_path)
            agent_class = getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            raise ValueError(f"Failed to import agent class '{class_path}': {e}")

        # Check if it's a valid agent class
        # Precondition: agent_class must be a subclass of Agent
        assert issubclass(agent_class, Agent), f"{class_name} is not a subclass of Agent"

        # Remove class from kwargs to avoid passing it to constructor
        constructor_args = config.copy()
        constructor_args.pop("class", None)

        # Extract yaml_path and use_default_config explicitly
        yaml_path = constructor_args.get("yaml_path")
        use_default_config = constructor_args.get("use_default_config", False)

        # Create and return the agent instance
        agent = agent_class(id=constructor_args.get("id"), yaml_path=yaml_path, use_default_config=use_default_config)

        # Postcondition: agent must be an instance of the specified class
        assert isinstance(agent, agent_class), f"Created agent is not an instance of {class_name}"

        return agent

    def load_config_from_file(self, yaml_path: str, merge: bool = False) -> None:
        """
        Load configuration from a YAML file

        Args:
            yaml_path: Path to the YAML configuration file
            merge: If True, merge with existing config instead of replacing it
        """
        # Precondition: yaml_path must be a non-empty string
        assert yaml_path and isinstance(yaml_path, str), "yaml_path must be a non-empty string"
        # Precondition: merge must be a boolean
        assert isinstance(merge, bool), "merge must be a boolean"

        path = Path(yaml_path)
        # Precondition: yaml_path must exist
        assert path.exists(), f"Config file not found: {yaml_path}"

        with open(path, "r") as file:
            new_config = yaml.safe_load(file)

        # Postcondition: new_config must be a dictionary
        assert isinstance(new_config, dict), "Loaded config must be a dictionary"

        if merge:
            # Deep merge of configs
            self._deep_merge_configs(self.config, new_config)
        else:
            # Replace existing config
            self.config = new_config

        if "tasks" in self.config:
            # Precondition: tasks must be a dictionary if present
            assert isinstance(self.config["tasks"], dict), "Tasks in config must be a dictionary"
            self.tasks = self.config["tasks"]
            # Re-validate after loading tasks
            self._validate_names()

        # Invariant: self.config must have been updated
        assert self.config, "self.config must be non-empty after loading config"

    def _deep_merge_configs(self, base: Dict[str, Any], overlay: Dict[str, Any]) -> None:
        """
        Deep merge two configuration dictionaries, with overlay taking precedence.

        Args:
            base: Base configuration dictionary to be updated
            overlay: Overlay configuration to be merged into base
        """
        # Precondition: both inputs must be dictionaries
        assert isinstance(base, dict), "base must be a dictionary"
        assert isinstance(overlay, dict), "overlay must be a dictionary"

        for key, value in overlay.items():
            # If both values are dictionaries, recursively merge them
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge_configs(base[key], value)
            else:
                # Otherwise, overlay takes precedence
                base[key] = value

        # Postcondition: base has been updated with overlay values
        assert all(key in base for key in overlay.keys()), "All overlay keys must be in the merged base"

    def _validate_names(self) -> None:
        """
        Validate that:
        1. Task names are unique
        2. Agent method names and task names don't conflict
        3. Global tool names don't conflict with agent methods or task names
        """
        # Precondition: self.tasks must be a dictionary
        assert isinstance(self.tasks, dict), "Agent tasks must be a dictionary"

        # Get all task names
        task_names = set(self.tasks.keys())

        # Get all agent method names (only public methods)
        agent_methods = {name for name, member in inspect.getmembers(self) if inspect.ismethod(member) and not name.startswith("_")}

        # Get all global tool names
        global_tools = set(_GLOBAL_TOOLS.keys())

        # Check for conflicts between task names and agent methods
        task_method_conflicts = task_names.intersection(agent_methods)
        assert not task_method_conflicts, f"Task names cannot conflict with agent methods. Conflicts: {task_method_conflicts}"

        # Check for conflicts between task names and global tools
        task_tool_conflicts = task_names.intersection(global_tools)
        assert not task_tool_conflicts, f"Task names cannot conflict with global tools. Conflicts: {task_tool_conflicts}"

        # Check for conflicts between agent methods and global tools
        method_tool_conflicts = agent_methods.intersection(global_tools)
        assert not method_tool_conflicts, f"Agent methods cannot conflict with global tools. Conflicts: {method_tool_conflicts}"

        # Postcondition: All validation checks passed

    async def run(self, _name: str, **kwargs):
        """
        Unified run method for tasks, functions, and tools

        Args:
            _name: Name of the task, function, or tool to run
            **kwargs: Parameters to pass to the task, function, or tool

        Returns:
            Result of the execution
        """
        # Precondition: _name must be a non-empty string
        assert isinstance(_name, str) and _name.strip(), "Task/function name must be a non-empty string"
        # Precondition: kwargs must be a dictionary
        assert isinstance(kwargs, dict), "kwargs must be a dictionary"

        # Add the agent's config to the data store
        self.data_store["config"] = self.config

        # Always add the agent's ID to the data store
        self.data_store["agent_id"] = self.id

        # Save all kwargs to the data store
        initial_data_store_size = len(self.data_store)
        self.data_store.update(kwargs)

        # Invariant: Data store should have been updated with kwargs
        assert len(self.data_store) >= initial_data_store_size, "Data store should be updated with kwargs"
        # Postcondition: data_store must contain config and agent_id
        assert "config" in self.data_store, "data_store must contain the agent's config"
        assert "agent_id" in self.data_store, "data_store must contain the agent's ID"

        # Check if it's a task
        if _name in self.tasks:
            task = self.tasks[_name]
            # Precondition: task must be a dictionary
            assert isinstance(task, dict), f"Task {_name} must be a dictionary"

            pipeline = task.get("pipeline", [])
            # Precondition: pipeline must be a list
            assert isinstance(pipeline, list), f"Pipeline for task {_name} must be a list"

            # Log warning if pipeline is empty
            if not pipeline:
                logger.warning(f"Task '{_name}' has an empty pipeline in agent '{self.id}'")

            initial_data_store_size = len(self.data_store)

            for step in pipeline:
                # Precondition: step must be a string
                assert isinstance(step, str), f"Pipeline step must be a string in task {_name}"

                result = await self.run(step)

                # Check if the step returned a should_exit flag
                if isinstance(result, dict) and result.get("should_exit", False):
                    logger.info(f"Exiting pipeline for task '{_name}' early due to should_exit flag from step '{step}'")
                    break

            # Postcondition: Data store should have been updated after pipeline execution
            assert len(self.data_store) >= initial_data_store_size, "Data store should be updated after pipeline execution"

            return self.data_store

        # Get the method to run
        if _name in _GLOBAL_TOOLS:
            method = _GLOBAL_TOOLS[_name]
        elif hasattr(self, _name) and callable(getattr(self, _name)):
            method = getattr(self, _name)
        else:
            raise ValueError(f"Function or task '{_name}' not found in agent {self.id}")

        # Precondition: method must be callable
        assert callable(method), f"'{_name}' is not callable"

        # Get parameters from state
        sig = inspect.signature(method)
        params = {}

        # Add data_store parameter if the method accepts it
        if "data_store" in sig.parameters:
            params["data_store"] = self.data_store

        # Handle required parameters
        required_params = [
            param_name for param_name, param in sig.parameters.items() if param.default == param.empty and param_name != "data_store"
        ]

        for param in required_params:
            # Check direct state
            if param in self.data_store:
                params[param] = self.data_store[param]
                continue

            # Check nested state
            name_state = self.data_store.get(_name, {})
            if param in name_state:
                params[param] = name_state[param]
                continue

            # Precondition: All required parameters must be available
            raise ValueError(f"Required parameter '{param}' not found in state for {_name}")

        # Handle optional parameters
        optional_params = [param for param in sig.parameters.keys() if param not in required_params and param != "data_store"]

        for param in optional_params:
            if param in self.data_store:
                params[param] = self.data_store[param]
            elif param in self.data_store.get(_name, {}):
                params[param] = self.data_store[_name][param]

        # Precondition: All required parameters must be in params
        assert all(param in params for param in required_params), f"All required parameters must be in params for {_name}"

        # Execute the method
        result = await method(**params)

        # Update data store with the result
        if isinstance(result, dict):
            # Check if result has a 'values' field with data to be shared in data_store
            if "values" in result and isinstance(result["values"], dict):
                # Add each key-value pair from values to the data_store
                for key, value in result["values"].items():
                    self.data_store[key] = value
                # Ensure invariant: values has been added to data_store
                assert all(k in self.data_store for k in result["values"].keys()), "All values must be added to data_store"
            # Don't update the data_store if no values field is provided
        else:
            self.data_store[_name] = result

        # Postcondition: Data store should contain the result if it was non-dict or had values
        assert (
            not isinstance(result, dict) or "values" not in result or any(k in self.data_store for k in result["values"].keys())
        ), "Data store should contain values if provided"

        return result
