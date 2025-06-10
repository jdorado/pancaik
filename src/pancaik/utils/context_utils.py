"""
Context utility functions for Pancaik tools.
"""

from typing import Any, Dict, Optional, Tuple


def find_and_extract_context_key(context: Dict[str, Any], target_key: str) -> Tuple[Optional[Any], Dict[str, Any]]:
    """
    Find a key in context that contains the target key (case-insensitive, space-insensitive) and extract its value.

    Args:
        context: The context dictionary to search in
        target_key: The key to search for (e.g., "image style", "video style")

    Returns:
        Tuple of (found_value, updated_context) where updated_context has the key removed
    """
    if not context or not isinstance(context, dict):
        return None, context.copy() if context else {}

    # Normalize target key: lowercase and remove spaces
    normalized_target = target_key.lower().replace(" ", "")

    # Search for key containing the target
    found_key = None
    found_value = None

    for key in context.keys():
        if isinstance(key, str):
            normalized_key = key.lower().replace(" ", "")
            if normalized_target in normalized_key:
                found_key = key
                found_value = context[key]
                break

    # Create updated context without the found key
    updated_context = context.copy()
    if found_key:
        del updated_context[found_key]

    return found_value, updated_context
