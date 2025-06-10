"""
RetellAI API utility functions.

This module provides utility functions for interacting with the RetellAI API.
"""

import aiohttp
from typing import Dict, Any, Optional

from ...core.config import logger


async def create_phone_call(
    api_token: str,
    from_number: str,
    to_number: str,
    metadata: Optional[Dict[str, Any]] = None,
    retell_llm_dynamic_variables: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a phone call using the RetellAI API.
    
    Args:
        api_token: RetellAI API token
        from_number: Phone number to call from (format: +1XXXXXXXXXX)
        to_number: Phone number to call to (format: +1XXXXXXXXXX)
        metadata: Optional metadata for the call
        retell_llm_dynamic_variables: Optional dynamic variables for the LLM
        
    Returns:
        Dictionary containing the API response
        
    Raises:
        ValueError: If the API call fails
        aiohttp.ClientError: If there's a network error
    """
    payload = {
        "from_number": from_number,
        "to_number": to_number,
        "metadata": metadata or {},
        "retell_llm_dynamic_variables": retell_llm_dynamic_variables or {}
    }

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.retellai.com/v2/create-phone-call",
                headers=headers,
                json=payload
            ) as response:
                if response.status == 200 or response.status == 201:
                    api_response = await response.json()
                    logger.info(f"Successfully created RetellAI call with ID: {api_response.get('call_id')}")
                    return api_response
                else:
                    error_text = await response.text()
                    error_msg = f"RetellAI API call failed with status {response.status}: {error_text}"
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                    
    except aiohttp.ClientError as e:
        error_msg = f"Network error during RetellAI API call: {str(e)}"
        logger.error(error_msg)
        raise aiohttp.ClientError(error_msg)


async def get_call_status(api_token: str, call_id: str) -> Dict[str, Any]:
    """
    Get the status of a phone call using the RetellAI API.
    
    Args:
        api_token: RetellAI API token
        call_id: The call ID to check status for
        
    Returns:
        Dictionary containing the call status and details
        
    Raises:
        ValueError: If the API call fails
        aiohttp.ClientError: If there's a network error
    """
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.retellai.com/v2/get-call/{call_id}",
                headers=headers
            ) as response:
                if response.status == 200:
                    api_response = await response.json()
                    logger.info(f"Successfully retrieved call status for ID: {call_id}")
                    return api_response
                else:
                    error_text = await response.text()
                    error_msg = f"RetellAI get call status failed with status {response.status}: {error_text}"
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                    
    except aiohttp.ClientError as e:
        error_msg = f"Network error during RetellAI get call status: {str(e)}"
        logger.error(error_msg)
        raise aiohttp.ClientError(error_msg) 