"""
API Request tool for making HTTP requests to external APIs.

This module provides functionality to make HTTP requests with customizable methods,
headers, and response handling. It supports both GET and POST requests with optional
custom processing of responses.
"""

import json
from typing import Any, Dict, Optional

import aiohttp
from pydantic import BaseModel, HttpUrl, validator

from ..core.ai_logger import ai_logger
from .base import tool


class APIRequestConfig(BaseModel):
    """Validation model for API request configuration."""

    api_url: HttpUrl
    http_method: str
    request_body: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, Any]] = None
    response_handling: str
    custom_processing: Optional[str] = None

    @validator("http_method")
    def validate_http_method(cls, v):
        if v.lower() not in ["get", "post"]:
            raise ValueError("HTTP method must be either GET or POST")
        return v.lower()

    @validator("response_handling")
    def validate_response_handling(cls, v):
        if v not in ["full", "data_only", "custom"]:
            raise ValueError("Invalid response handling option")
        return v


@tool()
async def api_request(
    data_store: Dict[str, Any],
    api_url: str,
    http_method: str = "get",
    request_body: Optional[str] = None,
    headers: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Make HTTP requests to external APIs with customizable configuration.

    Args:
        data_store: Agent's data store containing configuration and state
        api_url: The URL to make the request to
        http_method: HTTP method (GET or POST)
        request_body: JSON string containing request body for POST requests
        headers: JSON string containing custom headers

    Returns:
        Dictionary containing the API response
    """
    # Preconditions
    assert data_store is not None, "data_store must be provided"
    assert api_url, "api_url must be provided"

    # Extract agent info for logging
    agent_id = data_store.get("agent_id")
    config = data_store.get("config", {})
    account_id = config.get("account_id")
    agent_name = config.get("name")

    # Parse and validate inputs
    parsed_body = json.loads(request_body) if request_body else None
    parsed_headers = json.loads(headers) if headers else {}

    # Validate HTTP method
    if http_method.lower() not in ["get", "post"]:
        raise ValueError("HTTP method must be either GET or POST")

    # Prepare request
    request_kwargs = {"headers": parsed_headers or {}, "ssl": False}  # For development/testing - adjust based on needs
    if parsed_body and http_method.lower() == "post":
        request_kwargs["json"] = parsed_body

    ai_logger.action(f"Executing {http_method.upper()} request to {api_url}", agent_id, account_id, agent_name)

    # Make request
    async with aiohttp.ClientSession() as session:
        async with getattr(session, http_method.lower())(str(api_url), **request_kwargs) as response:
            status = response.status
            response_data = await response.json()

            # Check for empty/None response data even with successful status
            if response_data is None or (isinstance(response_data, (dict, list)) and not response_data):
                error_msg = "API returned empty or null response"
                ai_logger.warning(error_msg, agent_id, account_id, agent_name)
                raise ValueError(error_msg)

    context = {"api_response": response_data}

    ai_logger.result(f"API request completed successfully with status {status}", agent_id, account_id, agent_name)

    return {"values": {"context": context, "output": context}}
