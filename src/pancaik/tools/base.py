"""
Base module for tool definitions and registration.
"""

from functools import wraps
from typing import Any, Callable, Dict, List, Optional

from ..core.ai_logger import ai_logger

_GLOBAL_TOOLS: Dict[str, Callable] = {}


def tool(*args, agents: Optional[List[str]] = None) -> Callable:
    """
    Decorator to register a function as a global tool

    Args:
        *args: To support both @tool and @tool() syntax
        agents: List of required agent names
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                # Extract data_store from kwargs if available
                data_store: Dict[str, Any] = kwargs.get("data_store", {})
                agent_id = data_store.get("agent_id")
                config = data_store.get("config", {})
                account_id = config.get("account_id")
                agent_name = config.get("name")

                return await func(*args, **kwargs)
            except Exception as e:
                # Log error with AI logger if we have agent context
                if agent_id and account_id:
                    ai_logger.error(
                        f"Tool execution failed: [{func.__name__}] {str(e)}",
                        agent_id=agent_id,
                        account_id=account_id,
                        agent_name=agent_name,
                    )

                # Modify the error message to include the tool name
                e.args = (f"[{func.__name__}] {str(e)}", *e.args[1:])
                raise

        # Validate agent configurations exist
        if agents:
            from ..core.agent_registry import _AGENT_REGISTRY

            for name in agents:
                assert name in _AGENT_REGISTRY, f"Agent configuration {name} not found in registry"

        wrapper._required_agents = agents or []
        _GLOBAL_TOOLS[func.__name__] = wrapper
        return func

    # Handle both @tool and @tool() syntax
    if len(args) == 1 and callable(args[0]):
        return decorator(args[0])
    return decorator


class BaseTool:
    """Base class for all tools"""
