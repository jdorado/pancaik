"""
Custom webhook tools for agents.

This module provides tools for sending data to custom HTTP endpoints.
"""

import aiohttp
from typing import Any, Dict, Optional
from ..core.config import logger
from .base import tool


@tool
async def custom_webhook(
    webhook_url: str,
    output: Dict[str, Any],
    custom_headers: Optional[Dict[str, str]] = None,
    timeout: int = 30
):
    """
    Sends data to a custom HTTP endpoint using POST method.

    Args:
        webhook_url: The URL of the webhook endpoint
        output: The data payload to send
        custom_headers: Optional custom headers for the request
        timeout: Request timeout in seconds (default: 30)

    Returns:
        Dictionary with webhook operation results
    """
    # Preconditions
    assert webhook_url, "Webhook URL must be provided"
    assert output, "Data payload must be provided"
    
    # Set up request headers
    request_headers = {
        "Content-Type": "application/json",
        **(custom_headers or {})
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url=webhook_url,
                json=output,
                headers=request_headers,
                timeout=timeout
            ) as response:
                response_data = await response.json()
                status_code = response.status

                if 200 <= status_code < 300:
                    logger.info(f"Successfully sent webhook to {webhook_url}")
                    return {
                        "status": "success",
                        "status_code": status_code,
                        "response": response_data,
                        "values": {
                            "webhook_status": "success",
                            "webhook_response": response_data,
                            "webhook_url": webhook_url
                        }
                    }
                else:
                    logger.error(f"Webhook request failed with status {status_code}: {response_data}")
                    return {
                        "status": "error",
                        "status_code": status_code,
                        "error": f"Request failed with status {status_code}",
                        "response": response_data,
                        "values": {
                            "webhook_status": "error",
                            "webhook_error": f"Request failed with status {status_code}",
                            "webhook_url": webhook_url
                        }
                    }

    except aiohttp.ClientError as e:
        error_msg = f"HTTP client error when sending webhook: {str(e)}"
        logger.error(error_msg)
        return {
            "status": "error",
            "error": error_msg,
            "values": {
                "webhook_status": "error",
                "webhook_error": error_msg,
                "webhook_url": webhook_url
            }
        }
    except Exception as e:
        error_msg = f"Unexpected error when sending webhook: {str(e)}"
        logger.error(error_msg)
        return {
            "status": "error",
            "error": error_msg,
            "values": {
                "webhook_status": "error",
                "webhook_error": error_msg,
                "webhook_url": webhook_url
            }
        } 