"""
API Request tool for making HTTP requests to external APIs.

This module provides functionality to make HTTP requests with customizable methods,
headers, and response handling. It supports both GET and POST requests with optional
custom processing of responses.
"""

from typing import Any, Dict, Optional, Literal
import json
import aiohttp
from pydantic import BaseModel, HttpUrl, validator

from ..core.config import logger
from ..core.ai_logger import ai_logger
from ..utils.json_parser import extract_json_content
from ..utils.prompt_utils import get_prompt
from ..utils.ai_router import get_completion
from .base import tool


class APIRequestConfig(BaseModel):
    """Validation model for API request configuration."""
    api_url: HttpUrl
    http_method: str
    request_body: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, Any]] = None
    response_handling: str
    custom_processing: Optional[str] = None
    error_handling: Literal['stop', 'continue'] = 'stop'

    @validator('http_method')
    def validate_http_method(cls, v):
        if v.lower() not in ['get', 'post']:
            raise ValueError('HTTP method must be either GET or POST')
        return v.lower()

    @validator('response_handling')
    def validate_response_handling(cls, v):
        if v not in ['full', 'data_only', 'custom']:
            raise ValueError('Invalid response handling option')
        return v


@tool()
async def api_request(
    data_store: Dict[str, Any],
    api_url: str,
    http_method: str = 'get',
    request_body: Optional[str] = None,
    headers: Optional[str] = None,
    response_handling: str = 'data_only',
    custom_processing: Optional[str] = None,
    error_handling: str = 'stop'
) -> Dict[str, Any]:
    """
    Make HTTP requests to external APIs with customizable configuration.

    Args:
        data_store: Agent's data store containing configuration and state
        api_url: The URL to make the request to
        http_method: HTTP method (GET or POST)
        request_body: JSON string containing request body for POST requests
        headers: JSON string containing custom headers
        response_handling: How to process the response (full/data_only/custom)
        custom_processing: Instructions for custom response processing
        error_handling: How to handle errors ('stop' or 'continue')

    Returns:
        Dictionary containing the API response and processing results
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
    try:
        parsed_body = json.loads(request_body) if request_body else None
        parsed_headers = json.loads(headers) if headers else {}
        
        config = APIRequestConfig(
            api_url=api_url,
            http_method=http_method,
            request_body=parsed_body,
            headers=parsed_headers,
            response_handling=response_handling,
            custom_processing=custom_processing,
            error_handling=error_handling
        )
    except (json.JSONDecodeError, ValueError) as e:
        error_msg = f"Input validation error: {str(e)}"
        ai_logger.error(error_msg, agent_id, account_id, agent_name)
        return {
            "values": {
                "context": {"error": str(e)},
                "output": {"status": "error", "message": str(e)}
            },
            "should_exit": error_handling == 'stop'
        }

    # Prepare request
    request_kwargs = {
        "headers": config.headers or {},
        "ssl": False  # For development/testing - adjust based on needs
    }
    if config.request_body and config.http_method == 'post':
        request_kwargs["json"] = config.request_body

    ai_logger.action(
        f"Executing {config.http_method.upper()} request to {config.api_url}",
        agent_id,
        account_id,
        agent_name
    )

    # Make request
    try:
        async with aiohttp.ClientSession() as session:
            async with getattr(session, config.http_method)(
                str(config.api_url),
                **request_kwargs
            ) as response:
                status = response.status
                response_data = await response.json()

                # Check for empty/None response data even with successful status
                if response_data is None or (isinstance(response_data, (dict, list)) and not response_data):
                    error_msg = "API returned empty or null response"
                    ai_logger.warning(error_msg, agent_id, account_id, agent_name)
                    return {
                        "values": {
                            "context": {"error": error_msg, "status_code": status},
                            "output": {"status": "error", "message": error_msg}
                        },
                        "should_exit": config.error_handling == 'stop'
                    }

    except Exception as e:
        error_msg = f"API request error: {str(e)}"
        ai_logger.error(error_msg, agent_id, account_id, agent_name)
        return {
            "values": {
                "context": {"error": str(e)},
                "output": {"status": "error", "message": str(e)}
            },
            "should_exit": config.error_handling == 'stop'
        }

    # Process response based on handling option
    result = {
        "status_code": status,
        "headers": dict(response.headers),
    }

    if config.response_handling == 'full':
        result["data"] = response_data
    elif config.response_handling == 'data_only':
        result = response_data
    elif config.response_handling == 'custom' and config.custom_processing:
        ai_logger.thinking(
            "Processing API response with custom instructions",
            agent_id,
            account_id,
            agent_name
        )
        # Process using LLM if custom processing is requested
        prompt_data = {
            "task": "Process API response according to instructions",
            "response_data": response_data,
            "instructions": config.custom_processing,
        }
        prompt = get_prompt(prompt_data)
        model_id = data_store.get("config", {}).get("ai_models", {}).get("default")
        
        try:
            llm_response = await get_completion(prompt=prompt, model_id=model_id)
            processed_result = extract_json_content(llm_response) or llm_response
            result = processed_result
        except Exception as e:
            error_msg = f"Custom processing error: {str(e)}"
            ai_logger.error(error_msg, agent_id, account_id, agent_name)
            result["processing_error"] = str(e)
            result["raw_data"] = response_data
            return {
                "values": {
                    "context": {"error": str(e)},
                    "output": {"status": "error", "message": str(e)}
                },
                "should_exit": config.error_handling == 'stop'
            }

    context = {
        "api_response": result
    }

    ai_logger.result(
        f"API request completed successfully with status {status}",
        agent_id,
        account_id,
        agent_name
    )

    return {
        "values": {
            "context": context,
            "output": context
        }
    } 