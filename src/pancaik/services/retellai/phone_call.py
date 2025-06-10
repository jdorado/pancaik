"""
RetellAI phone call tools for agents.

This module provides tools for making AI-powered phone calls with intelligent voice agents.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ...core.ai_logger import ai_logger
from ...core.config import get_config, logger
from ...core.connections import ConnectionHandler
from ...tools.base import tool
from ...utils.ai_router import get_completion
from ...utils.json_parser import extract_json_content
from ...utils.prompt_utils import get_prompt
from .api_utils import create_phone_call, get_call_status


def parse_us_phone_number(phone_number: str) -> str:
    """
    Parse and normalize a US phone number to the format +12345678901.

    Removes spaces, dashes, parentheses, dots, and other special characters.
    Validates that it's a proper 10-digit US number according to NANP rules and adds +1 prefix.

    Args:
        phone_number: Raw phone number string

    Returns:
        Normalized phone number in format +12345678901

    Raises:
        ValueError: If the phone number cannot be parsed as a valid US number
    """
    if not phone_number:
        raise ValueError("Phone number cannot be empty")

    # Remove all non-digit characters
    digits_only = re.sub(r"[^\d]", "", phone_number)

    # Handle different US number formats
    if len(digits_only) == 10:
        # 10 digits: assume US number, add country code
        normalized = f"+1{digits_only}"
        area_code = digits_only[:3]
        exchange = digits_only[3:6]
        number = digits_only[6:]
    elif len(digits_only) == 11 and digits_only.startswith("1"):
        # 11 digits starting with 1: US number with country code
        normalized = f"+{digits_only}"
        area_code = digits_only[1:4]
        exchange = digits_only[4:7]
        number = digits_only[7:]
    else:
        raise ValueError(
            f"Invalid US phone number format: {phone_number}. Expected 10 digits (US number) or 11 digits starting with 1 (US number with country code). Got {len(digits_only)} digits: {digits_only}"
        )

    # Validate the final format - must be exactly +1 followed by 10 digits
    if not re.match(r"^\+1\d{10}$", normalized):
        raise ValueError(f"Failed to normalize phone number: {phone_number}. Result '{normalized}' does not match +1XXXXXXXXXX format")

    # Ensure we have exactly 3-3-4 digit breakdown for validation
    if len(area_code) != 3 or len(exchange) != 3 or len(number) != 4:
        raise ValueError(f"Invalid phone number structure: area_code={area_code}, exchange={exchange}, number={number}")

    # Validate NANP (North American Numbering Plan) rules
    # Area code validation
    if area_code[0] in ["0", "1"]:
        raise ValueError(f"Invalid area code {area_code}: first digit cannot be 0 or 1")
    if area_code[1] == "9" and area_code[2] == "1":
        raise ValueError(f"Invalid area code {area_code}: N9X format not allowed where X=1")

    # Exchange code validation
    if exchange[0] in ["0", "1"]:
        raise ValueError(f"Invalid exchange code {exchange}: first digit cannot be 0 or 1")

    # Check for invalid special service numbers
    if area_code == "555" and exchange.startswith("01"):
        # 555-01XX numbers are reserved for fictional use
        raise ValueError(f"Invalid phone number: 555-01XX numbers are reserved for fictional use")

    # Check for other invalid patterns
    if area_code == exchange == number[:3]:
        raise ValueError(f"Invalid phone number: area code, exchange, and first 3 digits of number cannot all be the same")

    return normalized


@tool()
async def phone_call(
    voice_connection: str,
    call_instructions: str,
    data_store: Optional[Dict[str, Any]] = None,
    resuming_from_step: Optional[str] = None,
    is_resuming: bool = False,
) -> Dict[str, Any]:
    """
    Make AI-powered phone calls with intelligent voice agents using RetellAI API.

    Configure the agent's objective, conversation context, and desired outcomes.
    The agent will conduct natural voice conversations based on your instructions.

    The function makes an actual HTTP request to the RetellAI API to initiate the call.

    Args:
        voice_connection: Connection ID for RetellAI credentials (must contain api_token/token,
                         from_number/phone_number, and optionally agent_id)
        call_instructions: Detailed instructions for the call including objective, context,
                         conversation guidelines, and desired outcomes
        data_store: Optional data store for additional context
        resuming_from_step: Name of the step being resumed from (if resuming)
        is_resuming: Whether this tool is being resumed from processing mode

    Returns:
        Dictionary with call results and context updates including the actual RetellAI call_id

    Raises:
        ValueError: If required credentials, phone numbers, or agent configuration is missing
    """

    # Check if we're resuming from this step (meaning call is in progress)
    if is_resuming and resuming_from_step == "phone_call":
        logger.info(f"Resuming phone_call step - checking call status")

        # Get call_id from data_store output
        call_id = "call_89e5be0032dd2b583b8885bb40a"  # TODO predent
        # TODO restore call_id = data_store.get("output", {}).get("call_id") if data_store else None
        if not call_id:
            error_msg = "Cannot resume phone_call: call_id not found in data_store"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Get API credentials
        db = get_config("db")
        if db is None:
            raise ValueError("Database not initialized in config")

        connection_handler = ConnectionHandler(db)
        voice_connection = data_store.get("output", {}).get("voice_connection_used", voice_connection)
        connection_params = await connection_handler.get_connection(voice_connection)
        if not connection_params:
            raise ValueError(f"Voice connection not found: {voice_connection}")

        api_token = connection_params.get("api_key")
        if not api_token:
            raise ValueError("API token not found in connection parameters")

        try:
            # Check call status using utility function
            call_status_response = await get_call_status(api_token, call_id)
            call_status = call_status_response.get("call_status", "unknown")

            # Check if call is still active
            active_statuses = ["registered", "ongoing", "in_progress"]
            call_still_active = call_status.lower() in active_statuses

            if call_still_active:
                # Call still in progress, continue processing
                logger.info(f"Call {call_id} still active with status: {call_status}")
                return {
                    "should_process": True,
                }
            else:
                # Call completed, return final status with complete response data
                logger.info(f"Call {call_id} completed with status: {call_status}")

                # Extract additional fields from the complete call response
                call_result = {
                    "call_id": call_id,
                    "to_number": call_status_response.get("to_number"),
                    "status": call_status_response.get("call_status"),
                    "start_timestamp": call_status_response.get("start_timestamp"),
                    "end_timestamp": call_status_response.get("end_timestamp"),
                    "transcript": call_status_response.get("transcript"),
                    "call_analysis": call_status_response.get("call_analysis"),
                }

                return {"values": {"output": {"call_result": call_result}}}
        except Exception as e:
            error_msg = f"Error checking call status for {call_id}: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    # TODO tmp pretend call scheduled
    # Extract AI logging context for pretend call
    agent_id = data_store.get("agent_id") if data_store else None
    account_id = data_store.get("config", {}).get("account_id") if data_store else None
    agent_name = data_store.get("config", {}).get("name") if data_store else None

    # Log the pretend call creation
    ai_logger.action(f"Creating pretend phone call with instructions: {call_instructions[:100]}...", agent_id, account_id, agent_name)

    # Create a mock call result for testing
    mock_call_id = "call_mock_123456789"
    call_result = {
        "call_id": mock_call_id,
        "call_status": "registered",
        "agent_id": "mock_agent_id",
        "from_number": "+15551234567",
        "to_number": "+15559876543",
        "start_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(f"Pretend call created with mock ID: {mock_call_id}")

    ai_logger.result(f"Successfully created pretend phone call with ID: {mock_call_id}", agent_id, account_id, agent_name)

    return {
        "status": "success",
        "should_process": True,
        "values": {"output": {"call_registration": call_result}},
    }

    # Preconditions (Design by Contract)
    assert isinstance(voice_connection, str) and voice_connection, "voice_connection must be a non-empty string"
    assert isinstance(call_instructions, str) and call_instructions, "call_instructions must be a non-empty string"

    # Extract AI logging context
    agent_id = data_store.get("agent_id") if data_store else None
    account_id = data_store.get("config", {}).get("account_id") if data_store else None
    agent_name = data_store.get("config", {}).get("name") if data_store else None
    config = data_store.get("config", {}) if data_store else {}

    logger.info(f"Initiating phone call for agent {agent_id} ({agent_name})")

    # Get database instance from config
    db = get_config("db")
    if db is None:
        raise ValueError("Database not initialized in config")

    # Initialize connection handler with db
    connection_handler = ConnectionHandler(db)

    # Get the connection parameters
    connection_params = await connection_handler.get_connection(voice_connection)
    if not connection_params:
        raise ValueError(f"Voice connection not found: {voice_connection}")

    # --- Tool logic: Phone call processing ---

    # Prepare the call using AI to structure the instructions
    prompt_data = {
        "task": "Analyze and structure the phone call instructions for an AI voice agent",
        "call_instructions": call_instructions,
        "context": data_store.get("context", {}) if data_store else {},
        "output_format": "OUTPUT IN JSON: Strict JSON format, no additional text",
        "evaluation_required": "Include a boolean 'sufficient_context' field indicating whether the provided context contains enough information to correctly proceed with the call based on the call instructions",
    }

    prompt = get_prompt(prompt_data)
    model_id = config.get("ai_models", {}).get("default")
    response = await get_completion(prompt=prompt, model_id=model_id)

    # Parse the response as strict JSON
    parsed_response = extract_json_content(response) or {}

    # Check if we have sufficient context to proceed
    sufficient_context = parsed_response.get("sufficient_context", False)
    if not sufficient_context:
        error_msg = "Insufficient context information to proceed with the phone call based on the provided instructions"
        logger.error(error_msg)
        ai_logger.error(error_msg, agent_id, account_id, agent_name)
        raise ValueError(error_msg)

    ai_logger.action(f"Creating phone call with instructions: {call_instructions[:100]}...", agent_id, account_id, agent_name)

    # Parse and validate phone numbers
    try:
        # Parse from_number from connection_params
        from_number_raw = connection_params.get("from_number") or connection_params.get("phone_number")
        if not from_number_raw:
            raise ValueError("from_number not found in connection parameters")
        from_number = parse_us_phone_number(from_number_raw)

        # Parse to_number from parsed_response
        to_number_raw = parsed_response.get("to_number")
        if not to_number_raw:
            raise ValueError("to_number not found in parsed response")
        to_number = parse_us_phone_number(to_number_raw)

        logger.info(f"Parsed phone numbers - From: {from_number}, To: {to_number}")

    except ValueError as e:
        error_msg = f"Phone number parsing failed: {str(e)}"
        logger.error(error_msg)
        ai_logger.error(error_msg, agent_id, account_id, agent_name)
        raise ValueError(error_msg)

    # Get API credentials from connection parameters
    api_token = connection_params.get("api_key")
    if not api_token:
        raise ValueError("API token not found in connection parameters")

    # Prepare dynamic variables by excluding specific keys
    excluded_keys = {"to_number", "sufficient_context"}
    retell_llm_dynamic_variables = {key: value for key, value in parsed_response.items() if key not in excluded_keys}

    # Prepare metadata and dynamic variables
    metadata = {
        "pancaik_agent_id": str(agent_id) if agent_id else None,
        "pancaik_agent_name": agent_name,
    }

    try:
        # Make the API call using utility function
        api_response = await create_phone_call(
            api_token=api_token,
            from_number=from_number,
            to_number=to_number,
            metadata=metadata,
            retell_llm_dynamic_variables=retell_llm_dynamic_variables,
        )

        # Extract and validate key response data
        call_id = api_response.get("call_id")
        call_status = api_response.get("call_status")

        if not call_id:
            error_msg = "RetellAI API response missing call_id"
            logger.error(error_msg)
            ai_logger.error(error_msg, agent_id, account_id, agent_name)
            raise ValueError(error_msg)

        # Check if call_status indicates an error
        if call_status and call_status.lower() in ["error", "failed", "disconnected"]:
            error_msg = f"RetellAI call failed with status: {call_status}"
            logger.error(error_msg)
            ai_logger.error(error_msg, agent_id, account_id, agent_name)
            raise ValueError(error_msg)

        call_result = {
            "call_id": call_id,
            "call_status": call_status or "unknown",
            "agent_id": api_response.get("agent_id"),
            "from_number": from_number,
            "to_number": to_number,
            "start_timestamp": api_response.get("start_timestamp"),
        }
        logger.info(f"Successfully initiated RetellAI call with ID: {call_id}, status: {call_status}")

    except Exception as e:
        error_msg = f"Error during RetellAI API call: {str(e)}"
        logger.error(error_msg)
        ai_logger.error(error_msg, agent_id, account_id, agent_name)
        raise ValueError(error_msg)

    call_id = call_result["call_id"]

    # Postconditions (Design by Contract)
    assert "call_id" in call_result, "Call results must contain 'call_id'"

    logger.info(f"Phone call created with ID: {call_id}")

    # Prepare result
    result = {
        "status": "success",
        "should_process": True,  # Always process after call since it's asynchronous
        "values": {"output": {"call_registration": call_result}},
    }

    ai_logger.result(f"Successfully created phone call with ID: {call_id}", agent_id, account_id, agent_name)

    return result
