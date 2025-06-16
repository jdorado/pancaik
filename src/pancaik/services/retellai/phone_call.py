"""
RetellAI phone call tools for agents.

This module provides tools for making AI-powered phone calls with intelligent voice agents.
"""

import re
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


def validate_flat_variables(variables: Dict[str, Any]) -> None:
    """
    Validate that all variables are flat (no nested objects or arrays).
    
    RetellAI API requires dynamic variables to be flat JSON with only
    string, number, or boolean values.
    
    Args:
        variables: Dictionary of dynamic variables to validate
        
    Raises:
        ValueError: If any variable contains nested objects or arrays
    """
    for key, value in variables.items():
        if isinstance(value, (dict, list)):
            raise ValueError(
                f"Dynamic variable '{key}' contains nested data (type: {type(value).__name__}). "
                f"RetellAI API requires flat JSON structure with only string, number, or boolean values. "
                f"Value: {value}"
            )
        elif not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError(
                f"Dynamic variable '{key}' has unsupported type: {type(value).__name__}. "
                f"Only string, number, boolean, or null values are allowed. Value: {value}"
            )


@tool()
async def phone_call(
    voice_connection: str,
    call_instructions: str,
    data_store: Optional[Dict[str, Any]] = None,
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

    Returns:
        Dictionary with call results and context updates including the actual RetellAI call_id

    Raises:
        ValueError: If required credentials, phone numbers, or agent configuration is missing
    """

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
        "dynamic_variables_requirement": "All dynamic variables (except 'to_number' and 'sufficient_context') must be flat key-value pairs with string, number, or boolean values only. NO nested objects or arrays are allowed as these will be passed to RetellAI API which requires flat JSON structure.",
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

    # Validate dynamic variables are flat (RetellAI API requirement)
    try:
        validate_flat_variables(retell_llm_dynamic_variables)
        logger.info(f"Dynamic variables validated as flat: {list(retell_llm_dynamic_variables.keys())}")
    except ValueError as e:
        error_msg = f"Dynamic variables validation failed: {str(e)}"
        logger.error(error_msg)
        ai_logger.error(error_msg, agent_id, account_id, agent_name)
        raise ValueError(error_msg)

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
    call_registration = {"call_registration": call_result}
    result = {
        "status": "success",
        "values": {"output": call_registration, "context": call_registration},
    }

    ai_logger.result(f"Successfully created phone call with ID: {call_id}", agent_id, account_id, agent_name)

    return result


@tool()
async def get_call_details(
    voice_connection: str,
    call_id: Optional[str] = None,
    data_store: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Get detailed information and status of a RetellAI phone call.

    Retrieves comprehensive call data including status, transcript, analysis, and metrics.
    Use this tool to check on calls initiated with the phone_call tool.

    Args:
        voice_connection: Connection ID for RetellAI credentials (must contain api_token/token)
        call_id: Optional unique identifier of the call to retrieve details for.
                If not provided, will attempt to retrieve from context (call_registration.call_id)
        data_store: Optional data store for additional context

    Returns:
        Dictionary with complete call details including status, transcript, and analysis

    Raises:
        ValueError: If required credentials or call_id is missing, or if call is not found
    """

    # Preconditions (Design by Contract)
    assert isinstance(voice_connection, str) and voice_connection, "voice_connection must be a non-empty string"

    # If call_id is not provided, try to get it from context
    if not call_id:
        if data_store:
            # Check in outputs for call_registration
            outputs = data_store.get("outputs", {})
            if "call_registration" in outputs:
                call_id = outputs["call_registration"].get("call_id")

            # Check in context for call_registration
            if not call_id:
                context = data_store.get("context", {})
                if "call_registration" in context:
                    call_id = context["call_registration"].get("call_id")

            # Check directly in context for call_id
            if not call_id:
                call_id = context.get("call_id")

            # Check directly in outputs for call_id
            if not call_id:
                call_id = outputs.get("call_id")

            # If still not found, use LLM to extract call_id from context
            if not call_id and (outputs or context):
                try:
                    config = data_store.get("config", {})
                    model_id = config.get("ai_models", {}).get("default")

                    prompt_data = {
                        "task": "Extract the call_id from the provided context data",
                        "context_data": {"outputs": outputs, "context": context},
                        "instructions": "Look for any call_id, call identifier, or phone call reference in the provided data. Return ONLY the call_id value as a plain string, no JSON or additional text.",
                        "output_format": "Return only the call_id string value, nothing else",
                    }

                    prompt = get_prompt(prompt_data)
                    llm_response = await get_completion(prompt=prompt, model_id=model_id)

                    # Clean the response to extract just the call_id
                    extracted_call_id = llm_response.strip().strip('"').strip("'")

                    # Validate that we got a reasonable call_id format
                    if extracted_call_id and len(extracted_call_id) > 5 and not extracted_call_id.lower().startswith("no"):
                        call_id = extracted_call_id
                        logger.info(f"LLM extracted call_id from context: {call_id}")

                except Exception as e:
                    logger.warning(f"Failed to extract call_id using LLM: {str(e)}")

        if not call_id:
            raise ValueError("call_id must be provided either as parameter or available in data_store (outputs/context sections)")

    assert isinstance(call_id, str) and call_id, "call_id must be a non-empty string"

    # Extract AI logging context
    agent_id = data_store.get("agent_id") if data_store else None
    account_id = data_store.get("config", {}).get("account_id") if data_store else None
    agent_name = data_store.get("config", {}).get("name") if data_store else None

    logger.info(f"Retrieving call details for call ID: {call_id}")

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

    # Get API credentials from connection parameters
    api_token = connection_params.get("api_key")
    if not api_token:
        raise ValueError("API token not found in connection parameters")

    try:
        # Check call status using utility function
        call_status_response = await get_call_status(api_token, call_id)

        # Validate response structure
        if not call_status_response or not isinstance(call_status_response, dict):
            logger.error(f"Invalid call status response for {call_id}: {call_status_response}")
            raise ValueError(f"Invalid call status response: expected dict, got {type(call_status_response)}")

        call_status = call_status_response.get("call_status", "unknown")

        # Extract essential fields for classification and analysis
        call_result = {
            "call_id": call_id,
            "to_number": call_status_response.get("to_number"),
            "status": call_status_response.get("call_status"),
            "start_timestamp": call_status_response.get("start_timestamp"),
            "end_timestamp": call_status_response.get("end_timestamp"),
            "duration_ms": call_status_response.get("duration_ms"),
            "disconnection_reason": call_status_response.get("disconnection_reason"),
            "transcript": call_status_response.get("transcript"),
            "call_analysis": call_status_response.get("call_analysis"),
            "raw_response": call_status_response,  # Include full response for debugging
        }

        # Log call outcome for classification purposes
        disconnection_reason = call_status_response.get("disconnection_reason")
        duration_ms = call_status_response.get("duration_ms", 0)

        # Create outcome summary for classification
        outcome_info = []
        if call_status == "error":
            outcome_info.append(f"FAILED: {disconnection_reason or 'unknown reason'}")
        elif disconnection_reason:
            outcome_info.append(f"ENDED: {disconnection_reason}")
        else:
            outcome_info.append(f"STATUS: {call_status}")

        # Add call analysis insights
        call_analysis = call_status_response.get("call_analysis", {})
        if call_analysis and isinstance(call_analysis, dict):
            call_successful = call_analysis.get("call_successful", False)
            in_voicemail = call_analysis.get("in_voicemail", False)
            user_sentiment = call_analysis.get("user_sentiment", "Unknown")

            outcome_info.append(f"Success: {call_successful}")
            if in_voicemail:
                outcome_info.append("Voicemail: Yes")
            if user_sentiment != "Unknown":
                outcome_info.append(f"Sentiment: {user_sentiment}")

        outcome_summary = " | ".join(outcome_info)
        logger.info(f"Call {call_id} details retrieved ({duration_ms}ms): {outcome_summary}")

        # Determine if call is still active
        active_statuses = ["registered", "ongoing", "in_progress"]
        is_active = call_status.lower() in active_statuses

        call_output = {
            "call_result": call_result,
            "is_active": is_active,
            "summary": outcome_summary,
        }

        result = {
            "status": "success",
            "values": {"output": call_output, "context": call_output},
        }

        ai_logger.result(f"Retrieved call details for {call_id}: {outcome_summary}", agent_id, account_id, agent_name)

        return result

    except Exception as e:
        error_msg = f"Error retrieving call details for {call_id}: {str(e)}"
        logger.error(error_msg)
        ai_logger.error(error_msg, agent_id, account_id, agent_name)
        raise ValueError(error_msg)
