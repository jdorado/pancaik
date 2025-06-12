"""
Custom webhook tools for agents.

This module provides tools for sending data to custom HTTP endpoints.
"""

import json
from typing import Any, Dict, Optional

import aiohttp

from ..core.ai_logger import ai_logger
from ..core.config import logger
from ..utils.ai_router import get_completion
from ..utils.json_parser import extract_json_content
from ..utils.prompt_utils import get_prompt
from .base import tool


class WebhookError(Exception):
    """Exception raised for webhook errors."""


@tool
async def custom_webhook(webhook_url: str, data_store: Dict[str, Any], instructions: Optional[str] = None, timeout: int = 30):
    """
    Sends data to a custom HTTP endpoint with LLM-parsed configuration instructions.

    Args:
        webhook_url: The URL of the webhook endpoint
        data_store: Agent's data store containing configuration, state and outputs
        instructions: Optional instructions for configuring the webhook request (method, headers, payload format, etc.)
        timeout: Request timeout in seconds (default: 30)

    Returns:
        Dictionary with webhook operation results including context and output values

    Raises:
        WebhookError: If the webhook request fails or configuration is invalid
    """
    # Extract agent info from data_store for AI logging
    agent_id = data_store.get("agent_id")
    config = data_store.get("config", {})
    account_id = config.get("account_id")
    agent_name = config.get("name")
    outputs = data_store.get("outputs", {})
    context = data_store.get("context", {})

    # Preconditions
    assert webhook_url, "Webhook URL must be provided"
    assert data_store, "Data store must be provided"
    assert outputs, "No outputs found in data store"

    ai_logger.thinking(f"Preparing to send webhook to {webhook_url}", agent_id=agent_id, account_id=account_id, agent_name=agent_name)

    # Default webhook configuration
    webhook_config = {
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "payload": outputs,
        "params": {}
    }

    # Parse instructions with LLM if provided
    if instructions and instructions.strip():
        ai_logger.thinking(f"Parsing webhook configuration instructions with LLM", agent_id=agent_id, account_id=account_id, agent_name=agent_name)
        
        prompt_data = {
            "task": "Parse webhook configuration instructions and generate webhook request configuration",
            "instructions": instructions,
            "outputs": outputs,
            "context": context,
            "webhook_url": webhook_url,
            "agent_name": agent_name,
            "system_instruction": """You are a webhook configuration parser. Given user instructions, generate a JSON configuration for an HTTP webhook request.

Available data:
- outputs: The agent's output data that will be sent
- context: Additional context data
- webhook_url: The target webhook URL

Parse the instructions and return a JSON object with these fields:
{
  "method": "GET|POST|PUT|PATCH|DELETE",
  "headers": {"key": "value"},
  "payload": {...},
  "params": {"key": "value"}
}

Instructions may include:
- HTTP method (default: POST)
- Custom headers (Authorization, Content-Type, etc.)
- Payload transformation (how to format/filter outputs)
- Query parameters
- Authentication setup
- Request metadata

If instructions are unclear or empty, use defaults:
- method: "POST"
- headers: {"Content-Type": "application/json"}
- payload: full outputs object
- params: {}

IMPORTANT: Return ONLY valid JSON, no explanations."""
        }

        try:
            prompt = get_prompt(prompt_data)
            model_id = config.get("ai_models", {}).get("default")
            response = await get_completion(prompt=prompt, model_id=model_id)
            
            # Parse AI response
            parsed_config = extract_json_content(response)
            if parsed_config and isinstance(parsed_config, dict):
                # Validate and merge configuration
                if "method" in parsed_config:
                    webhook_config["method"] = str(parsed_config["method"]).upper()
                if "headers" in parsed_config and isinstance(parsed_config["headers"], dict):
                    webhook_config["headers"].update(parsed_config["headers"])
                if "payload" in parsed_config:
                    webhook_config["payload"] = parsed_config["payload"]
                if "params" in parsed_config and isinstance(parsed_config["params"], dict):
                    webhook_config["params"] = parsed_config["params"]
                    
                ai_logger.action(f"Successfully parsed webhook instructions: {webhook_config['method']} with {len(webhook_config['headers'])} headers", 
                               agent_id=agent_id, account_id=account_id, agent_name=agent_name)
            else:
                ai_logger.action(f"Could not parse instructions, using defaults", agent_id=agent_id, account_id=account_id, agent_name=agent_name)
                
        except Exception as e:
            logger.warning(f"Error parsing webhook instructions with LLM: {e}, using defaults")
            ai_logger.action(f"Error parsing instructions, using defaults: {str(e)}", agent_id=agent_id, account_id=account_id, agent_name=agent_name)

    ai_logger.action(
        f"Sending {webhook_config['method']} webhook request with {len(webhook_config.get('payload', {}))} data fields", 
        agent_id=agent_id, account_id=account_id, agent_name=agent_name
    )

    # Prepare request parameters
    request_kwargs = {
        "url": webhook_url,
        "headers": webhook_config["headers"],
        "timeout": timeout
    }

    # Add query parameters if any
    if webhook_config["params"]:
        request_kwargs["params"] = webhook_config["params"]

    # Add payload for methods that support body
    if webhook_config["method"] in ["POST", "PUT", "PATCH"]:
        # Check if Content-Type suggests JSON
        content_type = webhook_config["headers"].get("Content-Type", "")
        if "application/json" in content_type:
            request_kwargs["json"] = webhook_config["payload"]
        else:
            request_kwargs["data"] = webhook_config["payload"]

    async with aiohttp.ClientSession() as session:
        # Get the appropriate method from session
        method_func = getattr(session, webhook_config["method"].lower())
        
        async with method_func(**request_kwargs) as response:
            status_code = response.status
            content_type = response.headers.get("Content-Type", "")

            if "application/json" in content_type:
                response_data = await response.json()
            else:
                response_data = await response.text()

            if 200 <= status_code < 300:
                logger.info(f"Successfully sent {webhook_config['method']} webhook to {webhook_url}")
                ai_logger.result(
                    f"Webhook request successful with status {status_code}", agent_id=agent_id, account_id=account_id, agent_name=agent_name
                )

                # Create context and output records
                output_record = {
                    "response": response_data,
                    "summary": f"{webhook_config['method']} webhook sent successfully to {webhook_url}",
                    "payload": webhook_config["payload"],
                    "method": webhook_config["method"],
                    "headers": webhook_config["headers"],
                    "params": webhook_config["params"]
                }

                # Postconditions
                assert "summary" in output_record, "Output must contain summary"

                return {"status": "success", "values": {"output": {"webhook": output_record}}}

            error_msg = f"Webhook request failed with status {status_code}: {response_data}"
            ai_logger.result(f"Webhook request failed: {error_msg}", agent_id=agent_id, account_id=account_id, agent_name=agent_name)
            raise WebhookError(error_msg)
