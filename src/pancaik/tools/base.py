from functools import wraps
from typing import Callable, Dict

_GLOBAL_TOOLS: Dict[str, Callable] = {}


def tool(func: Callable) -> Callable:
    """
    Decorator to register a function as a global tool

    Args:
        func: The function to register as a tool
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)

    _GLOBAL_TOOLS[func.__name__] = wrapper
    return func


class BaseTool:
    """Base class for all tools"""
