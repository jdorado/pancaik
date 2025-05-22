"""
Custom webhook tools for agents.

This module provides tools for sending data to custom HTTP endpoints.
"""

from typing import Any, Dict, Optional
import json

import aiohttp

from ..core.ai_logger import ai_logger
from ..core.config import logger
from .base import tool


class WebhookError(Exception):
    """Exception raised for webhook errors."""


@tool
async def custom_webhook(
    webhook_url: str, data_store: Dict[str, Any], custom_headers: Optional[str] = None, timeout: int = 30
):
    """
    Sends data to a custom HTTP endpoint using POST method.

    Args:
        webhook_url: The URL of the webhook endpoint
        data_store: Agent's data store containing configuration, state and outputs
        custom_headers: Optional JSON string containing custom headers for the request
        timeout: Request timeout in seconds (default: 30)

    Returns:
        Dictionary with webhook operation results including context and output values

    Raises:
        WebhookError: If the webhook request fails or if custom headers JSON is invalid
    """
    # Extract agent info from data_store for AI logging
    agent_id = data_store.get("agent_id")
    config = data_store.get("config", {})
    account_id = config.get("account_id")
    agent_name = config.get("name")
    outputs = data_store.get("outputs", {})

    # Preconditions
    assert webhook_url, "Webhook URL must be provided"
    assert data_store, "Data store must be provided"
    assert outputs, "No outputs found in data store"

    ai_logger.thinking(f"Preparing to send webhook to {webhook_url}", agent_id=agent_id, account_id=account_id, agent_name=agent_name)

    # Parse custom headers if provided
    parsed_headers = {}
    if custom_headers:
        try:
            parsed_headers = json.loads(custom_headers)
            if not isinstance(parsed_headers, dict):
                raise WebhookError("Custom headers must be a valid JSON object")
        except json.JSONDecodeError as e:
            raise WebhookError(f"Invalid JSON in custom headers: {str(e)}")

    # Set up request headers
    request_headers = {"Content-Type": "application/json", **parsed_headers}

    ai_logger.action(
        f"Sending webhook request with {len(outputs)} data fields", agent_id=agent_id, account_id=account_id, agent_name=agent_name
    )

    async with aiohttp.ClientSession() as session:
        async with session.post(url=webhook_url, json=outputs, headers=request_headers, timeout=timeout) as response:
            response_data = await response.json()
            status_code = response.status

            if 200 <= status_code < 300:
                logger.info(f"Successfully sent webhook to {webhook_url}")
                ai_logger.result(
                    f"Webhook request successful with status {status_code}", agent_id=agent_id, account_id=account_id, agent_name=agent_name
                )

                # Create context and output records
                output_record = {
                    "response": response_data,
                    "summary": f"Webhook sent successfully to {webhook_url}",
                    "payload": outputs,
                }

                # Postconditions
                assert "summary" in output_record, "Output must contain summary"

                return {"status": "success", "values": {"output": {"webhook": output_record}}}

            error_msg = f"Webhook request failed with status {status_code}: {response_data}"
            ai_logger.result(f"Webhook request failed: {error_msg}", agent_id=agent_id, account_id=account_id, agent_name=agent_name)
            raise WebhookError(error_msg)
