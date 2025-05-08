from functools import wraps
from typing import Callable, Dict
from ..core.config import logger

_GLOBAL_TOOLS: Dict[str, Callable] = {}


def tool(func: Callable) -> Callable:
    """
    Decorator to register a function as a global tool

    Args:
        func: The function to register as a tool
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            # Modify the error message to include the tool name
            e.args = (f"[{func.__name__}] {str(e)}", *e.args[1:])
            raise

    _GLOBAL_TOOLS[func.__name__] = wrapper
    return func


class BaseTool:
    """Base class for all tools"""
