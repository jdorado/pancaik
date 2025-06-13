"""
API Request Agent tool for making HTTP requests based on natural language instructions.

This module provides functionality to parse natural language instructions for API requests
and automatically extract the required parameters for the api_request tool.
"""

import json
from typing import Any, Dict, Optional

import aiohttp
from pydantic import BaseModel, HttpUrl, validator

from ..core.ai_logger import ai_logger
from ..utils.ai_router import get_completion
from ..utils.json_parser import extract_json_content
from ..utils.prompt_utils import get_prompt
from .base import tool


class APIRequestAgentConfig(BaseModel):
    api_url: HttpUrl
    http_method: str = "get"
    request_body: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, Any]] = None

    @validator("http_method")
    def validate_http_method(cls, v):
        if v.lower() not in ["get", "post"]:
            raise ValueError("HTTP method must be either GET or POST")
        return v.lower()


@tool()
async def api_request_agent(
    data_store: Dict[str, Any],
    api_instructions: str,
) -> Dict[str, Any]:
    """
    Parse natural language API instructions and execute API requests automatically.

    This tool uses an LLM to extract API request parameters from natural language instructions
    and then executes the API request directly.

    Args:
        data_store: Agent's data store containing configuration and state
        api_instructions: Natural language instructions describing the API request to make

    Returns:
        Dictionary containing the API response and processing results
    """
    assert data_store is not None, "data_store must be provided"
    assert api_instructions, "api_instructions must be provided"

    agent_id = data_store.get("agent_id")
    config = data_store.get("config", {})
    account_id = config.get("account_id")
    agent_name = config.get("name")

    prompt_data = {
        "task": "Extract API request parameters from natural language instructions",
        "instructions": api_instructions,
        "context": data_store.get("context", {}),
        "available_parameters": {
            "api_url": "Required: The URL to make the request to",
            "http_method": "Optional: HTTP method (GET or POST), defaults to 'get'",
            "request_body": "Optional: JSON string containing request body for POST requests",
            "headers": "Optional: JSON string containing custom headers",
            "proceed_if_no_results": "Optional: Whether to continue execution if API returns no results (true/false), defaults to true unless user explicitly states to stop",
        },
        "format_instructions": """
        Return a JSON object with the extracted parameters. Only include parameters that can be determined from the instructions.
        For request_body and headers, return them as JSON strings if they need to be included.
        Pay special attention to whether the user wants execution to stop if no results are returned from the API.
        Look for phrases like \"stop if no results\", \"exit if empty\", \"fail if no data\", etc.
        Default to proceed_if_no_results: true unless explicitly stated otherwise.
        Example output:
        {
            "api_url": "https://api.example.com/data",
            "http_method": "post",
            "request_body": "{\\"key\\": \\\"value\\"}",
            "headers": "{\\"Authorization\\": \\\"Bearer token\\"}",
            "proceed_if_no_results": true
        }
        """,
    }

    prompt = get_prompt(prompt_data)
    model_id = config.get("ai_models", {}).get("default")

    try:
        ai_logger.thinking("Extracting API parameters using LLM", agent_id, account_id, agent_name)
        llm_response = await get_completion(prompt=prompt, model_id=model_id)
        extracted_params = extract_json_content(llm_response)

        if not extracted_params:
            error_msg = "Failed to extract valid parameters from API instructions"
            ai_logger.error(error_msg, agent_id, account_id, agent_name)
            # Check if user explicitly requested to stop if extraction fails
            proceed_if_no_results = False
            if "proceed_if_no_results" in api_instructions.lower() and "false" in api_instructions.lower():
                proceed_if_no_results = False
            else:
                proceed_if_no_results = True
            if not proceed_if_no_results:
                return {"should_exit": True}
            else:
                ai_logger.warning("No parameters extracted but pipeline will continue", agent_id, account_id, agent_name)
                return None

        if "api_url" not in extracted_params:
            error_msg = "API URL is required but was not found in instructions"
            ai_logger.error(error_msg, agent_id, account_id, agent_name)
            # Check if user explicitly requested to stop if extraction fails
            proceed_if_no_results = False
            if "proceed_if_no_results" in api_instructions.lower() and "false" in api_instructions.lower():
                proceed_if_no_results = False
            else:
                proceed_if_no_results = True
            if not proceed_if_no_results:
                return {"should_exit": True}
            else:
                ai_logger.warning("API URL missing but pipeline will continue", agent_id, account_id, agent_name)
                return None

        ai_logger.result(f"Extracted API parameters: {extracted_params}", agent_id, account_id, agent_name)

        # Parse and validate inputs
        try:
            parsed_body = json.loads(extracted_params["request_body"]) if extracted_params.get("request_body") else None
            parsed_headers = json.loads(extracted_params["headers"]) if extracted_params.get("headers") else {}
            config_obj = APIRequestAgentConfig(
                api_url=extracted_params["api_url"],
                http_method=extracted_params.get("http_method", "get"),
                request_body=parsed_body,
                headers=parsed_headers,
            )
        except (json.JSONDecodeError, ValueError) as e:
            error_msg = f"Input validation error: {str(e)}"
            ai_logger.error(error_msg, agent_id, account_id, agent_name)
            return {"should_exit": True}

        request_kwargs = {"headers": config_obj.headers or {}, "ssl": False}
        if config_obj.request_body and config_obj.http_method == "post":
            request_kwargs["json"] = config_obj.request_body

        ai_logger.action(f"Executing {config_obj.http_method.upper()} request to {config_obj.api_url}", agent_id, account_id, agent_name)

        try:
            async with aiohttp.ClientSession() as session:
                async with getattr(session, config_obj.http_method)(str(config_obj.api_url), **request_kwargs) as response:
                    status = response.status
                    try:
                        response_data = await response.json()
                    except Exception:
                        response_data = await response.text()

                    proceed_if_no_results = extracted_params.get("proceed_if_no_results", True)
                    if response_data is None or (isinstance(response_data, (dict, list)) and not response_data):
                        error_msg = "API returned empty or null response"
                        if not proceed_if_no_results:
                            ai_logger.action("API returned no results and user specified not to proceed", agent_id, account_id, agent_name)
                            return {"should_exit": True}
                        else:
                            ai_logger.warning(error_msg + " - pipeline will continue", agent_id, account_id, agent_name)
                            return None
        except Exception as e:
            error_msg = f"API request error: {str(e)}"
            ai_logger.error(error_msg, agent_id, account_id, agent_name)
            return {"should_exit": True}

        context = {"api_response": response_data}

        ai_logger.result(f"API request completed successfully with status {status}", agent_id, account_id, agent_name)

        return {"values": {"context": context, "output": context}}

    except Exception as e:
        error_msg = f"Error processing API instructions: {str(e)}"
        ai_logger.error(error_msg, agent_id, account_id, agent_name)
        return {"should_exit": True}
