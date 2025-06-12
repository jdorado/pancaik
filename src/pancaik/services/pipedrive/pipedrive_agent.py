"""
Pipedrive CRM Agent Tool

This module provides an AI-powered agent that uses tool calling to interact with Pipedrive CRM.
The agent receives instructions and context, then uses LLM tool calling to execute specific
Pipedrive API functions directly. This allows for more precise and flexible CRM operations.

The agent will gradually expose Pipedrive API functions as callable tools to the LLM,
rather than being an all-encompassing Pipedrive agent.
"""

import json
import datetime
from typing import Any, Dict

from ...core.ai_logger import ai_logger
from ...core.config import get_config, logger
from ...core.connections import ConnectionHandler
from ...tools.base import tool
from ...utils.ai_router import get_completion
from ...utils.json_parser import extract_json_content
from ...utils.prompt_utils import get_prompt
from .pipedrive_cache import load_and_cache_pipedrive_metadata, simplify_pipedrive_metadata
from .pipedrive_client import PipedriveClient

OUTPUT_FORMAT = (
    """OUTPUT IN JSON: Strict JSON format, no additional text.\n{\n"
    "    \"success\": boolean,\n"
    "    \"results_found\": boolean,  // true if any matching data was found, false if not\n"
    "    \"data_summary\": \"string summary of data retrieved or why no results\",\n"
    "    \"should_exit\": boolean,  // true if user explicitly requested to stop if no results, else false or omitted\n"
    "    \"pipedrive_data\": \"relevant pipedrive data or null\"\n"
    "}"""
)

@tool()
async def pipedrive_agent(data_store: Dict[str, Any], pipedrive: str, pipedrive_instructions: str) -> Dict[str, Any]:
    """
    AI-powered Pipedrive CRM agent that uses tool calling to execute CRM operations.

    This agent receives natural language instructions and uses LLM tool calling to execute
    specific Pipedrive API functions. The LLM will have access to Pipedrive tools and can
    call them directly based on the instructions and context.

    Args:
        data_store: Agent's data store containing context, config, etc.
        pipedrive: Pipedrive connection ID
        pipedrive_instructions: Natural language instructions for CRM operations

    Returns:
        Dictionary with tool calling results and context updates
    """
    # Extract common context for logging and AI operations
    agent_id = data_store.get("agent_id")
    config = data_store.get("config", {})
    agent_name = config.get("name", "pipedrive_agent")
    account_id = config.get("account_id")
    context = data_store.get("context", {})

    # AI logging for initial analysis
    ai_logger.thinking(
        f"Starting Pipedrive CRM agent analysis for instructions: '{pipedrive_instructions[:100]}...' with connection ID: {pipedrive}",
        agent_id,
        account_id,
        agent_name,
    )

    logger.info(f"Running Pipedrive CRM agent for agent {agent_id} ({agent_name})")

    # Validate Pipedrive connection ID
    if not pipedrive:
        ai_logger.error("No Pipedrive connection ID provided - cannot proceed with CRM operations", agent_id, account_id, agent_name)
        logger.error(f"Pipedrive connection ID not provided for agent {agent_id}")
        return {"should_exit": True}

    # Get database instance from config
    db = get_config("db")
    if db is None:
        ai_logger.error("Database not initialized - cannot access Pipedrive connections", agent_id, account_id, agent_name)
        raise ValueError("Database not initialized in config")

    # Initialize connection handler with db
    connection_handler = ConnectionHandler(db)

    ai_logger.action(f"Retrieving Pipedrive connection details for connection ID: {pipedrive}", agent_id, account_id, agent_name)

    # Get the connection parameters
    connection_params = await connection_handler.get_connection(pipedrive)
    if not connection_params:
        ai_logger.error(
            f"Pipedrive connection '{pipedrive}' not found in database - please verify connection exists", agent_id, account_id, agent_name
        )
        raise ValueError(f"Pipedrive connection not found: {pipedrive}")

    # Get API token from connection parameters
    api_token = connection_params.get("api_token") or connection_params.get("token") or connection_params.get("api_key")
    if not api_token:
        ai_logger.error(
            "No API token found in Pipedrive connection parameters - authentication will fail", agent_id, account_id, agent_name
        )
        raise ValueError("API token not found in Pipedrive connection parameters")

    ai_logger.result(f"Successfully retrieved Pipedrive connection with API token", agent_id, account_id, agent_name)
    logger.info(f"Retrieved Pipedrive connection for agent {agent_id}")

    # Load and cache essential Pipedrive metadata (pipelines, stages, users, etc.)
    ai_logger.action("Loading Pipedrive metadata (pipelines, stages, users) from cache or API", agent_id, account_id, agent_name)

    try:
        cached_metadata = await load_and_cache_pipedrive_metadata(
            connection_handler=connection_handler,
            connection_id=pipedrive,
            api_token=api_token,
            force_refresh=False,  # Use cached data if available and valid
            cache_expiry_days=7,  # Cache expires after 1 week
        )

        metadata_summary = [f"{k}: {len(v) if isinstance(v, list) else 1}" for k, v in cached_metadata.items()]
        ai_logger.result(f"Successfully loaded Pipedrive metadata: {', '.join(metadata_summary)}", agent_id, account_id, agent_name)

        logger.info(f"Pipedrive metadata loaded for connection {pipedrive}")
        logger.debug(f"Cached items: {metadata_summary}")
    except Exception as cache_error:
        ai_logger.warning(
            f"Failed to load Pipedrive metadata cache: {str(cache_error)} - proceeding with limited context",
            agent_id,
            account_id,
            agent_name,
        )
        logger.warning(f"Failed to load Pipedrive metadata cache: {str(cache_error)}")
        cached_metadata = {}

    # Simplify cached metadata structure for the LLM
    simplified_metadata = simplify_pipedrive_metadata(cached_metadata)

    # Add current UTC datetime to context for LLM awareness
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    context["current_utc_datetime"] = now_utc.isoformat()  # e.g., '2024-06-07T12:34:56.789012+00:00'

    ai_logger.thinking(
        f"Prepared simplified metadata context for LLM with {len(simplified_metadata)} metadata categories",
        agent_id,
        account_id,
        agent_name,
    )

    try:
        # Initialize Pipedrive client
        ai_logger.action("Initializing Pipedrive client and creating tool calling capabilities", agent_id, account_id, agent_name)

        with PipedriveClient(api_token=api_token) as pipedrive_client:

            # Create LangChain tools from the client methods
            try:
                pipedrive_tools = pipedrive_client.create_tools()
            except ImportError:
                ai_logger.error(
                    "LangChain dependencies not installed - cannot create tool calling capabilities", agent_id, account_id, agent_name
                )
                raise ImportError("LangChain dependencies not installed. Run: poetry add langchain langchain-openai")

            # Create prompt for LLM with tool calling capabilities
            ai_logger.action(
                "Preparing comprehensive prompt with instructions, metadata context, and tool specifications",
                agent_id,
                account_id,
                agent_name,
            )

            prompt_data = {
                "instructions": pipedrive_instructions,
                "context": context,
                "connection_id": pipedrive,
                "agent_name": agent_name,
                "pipedrive_metadata": simplified_metadata,
                "available_tools": [
                    "get_activities - Get activities from Pipedrive CRM with optional filtering by deal_id, person_id, org_id, start_date, end_date, filter_id, limit. Use this tool to get activities that are due soon, due today, or overdue by filtering on due_date. If the user asks for 'activities due', use this tool with due_date filters."
                    "get_deals - Get deals from Pipedrive CRM with optional filtering by status, stage_id, owner, person, organization, pipeline, filter_id (Pipedrive filter ID), or ids[] (list of deal IDs)",
                    "get_persons - Get persons/contacts from Pipedrive CRM with optional filtering by person ID or organization",
                    "update_deal - Update an existing deal in Pipedrive CRM. Provide deal_id and the fields to update (e.g., pipeline_id, stage_id, value, title).",
                    "update_activity - Update an existing activity in Pipedrive CRM. Provide activity_id and the fields to update (e.g., subject, type, due_date, done, note).",
                    "create_activity - Add an activity to a deal in Pipedrive CRM (v2 API). Provide activity_data with at least: deal_id (required), subject (required), type (required), due_date (string, e.g., '2024-06-01'), due_time (string, e.g., '14:00' -- must be in 'HH:MM' 24-hour format, NOT 'HH:MM:SS'), done (boolean: finished or scheduled), note (body/description). Uses POST /api/v2/activities. Example: {\"due_date\": \"2024-06-01\", \"due_time\": \"14:00\"}",
                ],
                "output_format": OUTPUT_FORMAT,
            }

            prompt = get_prompt(prompt_data)

            # Create system message for the agent
            # Escape JSON braces to prevent template variable conflicts
            metadata_json = json.dumps(simplified_metadata, indent=2).replace("{", "{{").replace("}", "}}")
            context_json = json.dumps(context, indent=2).replace("{", "{{").replace("}", "}}") if context else "No additional context"

            system_message = f"""You are an expert Pipedrive CRM assistant for {agent_name}.

AVAILABLE TOOLS:
- get_activities: Retrieve activities from Pipedrive with filtering options (deal_id, person_id, org_id, start_date, end_date, filter_id, limit). Use this tool to get activities that are due soon, due today, or overdue by filtering on due_date. If the user asks for 'activities due', use this tool with due_date filters.
- get_deals: Retrieve deals from Pipedrive with filtering options (status, stage_id, owner_id, person_id, org_id, pipeline_id, filter_id, ids[])
- get_persons: Retrieve persons/contacts from Pipedrive with filtering options
- update_deal: Update an existing deal's fields (pipeline_id, stage_id, value, etc.)
- update_activity: Update an existing activity's fields (subject, type, due_date, done, note, etc.)
- create_activity: Add an activity to a deal in Pipedrive CRM (v2 API). Provide activity_data with at least:
  - 'deal_id' (the deal to attach the activity to, required)
  - 'subject' (required)
  - 'type' (required, e.g., call, meeting, task)
  - 'due_date' (string, e.g., '2024-06-01')
  - 'due_time' (string, e.g., '14:00' -- must be in 'HH:MM' 24-hour format, NOT 'HH:MM:SS')
  - 'done' (boolean: true for finished, false for scheduled)
  - 'note' (body/description)
- Uses POST /api/v2/activities. See Pipedrive v2 API docs for more details.

PIPEDRIVE METADATA CONTEXT:
{metadata_json}

INSTRUCTIONS:
1. Use the available tools step by step to gather all necessary information
2. Analyze the user's request carefully to determine what Pipedrive data they need
3. Call the appropriate tools with the correct filters based on the metadata context
4. Validate that the results match what the user requested
5. If the user asks for something specific (like a particular deal, stage, or person), verify it exists in the results
6. Provide clear error messages if the requested data cannot be found or if the request is invalid
7. If the user explicitly requests to stop or exit if no results are found, set 'should_exit' to true in your output. Otherwise, issue a warning in the output and continue with the pipeline.
8. If no results are found, this is NOT an error, but a valid result. Do NOT set error_message for this case; instead, set results_found: false and provide a data_summary or warning message explaining no results were found.

PARAMETER USAGE:
For get_activities:
- Use 'deal_id' to filter by deal
- Use 'person_id' to filter by person
- Use 'org_id' to filter by organization
- Use 'start_date' and 'end_date' to filter by date range
- Use 'filter_id' for filtering by Pipedrive filter ID
- Use 'limit' to control number of results returned (default: 100)

For get_deals:
- Use 'status' for deal outcomes: 'open', 'won', 'lost', 'deleted', 'all_not_deleted'
- Use 'stage_id' for specific stage filtering (numeric ID from metadata above)
- Use 'owner_id' for filtering by deal owner/user ID
- Use 'person_id' for filtering by associated contact/person
- Use 'org_id' for filtering by organization
- Use 'pipeline_id' for filtering by pipeline
- Use 'filter_id' for filtering by Pipedrive filter ID
- Use 'ids' for filtering by a list of deal IDs

For get_persons:
- Use 'person_id' to get a specific person by ID
- Use 'org_id' for filtering persons by organization ID
- Use 'limit' to control number of results returned (default: 100)

For update_deal:
- Always include the numeric 'deal_id' path parameter.
- Provide any fields to update in the body, such as 'pipeline_id', 'stage_id', 'value', 'title', etc.
- You can move a deal to another stage or pipeline by setting both 'pipeline_id' and 'stage_id' together.

For update_activity:
- Provide an activity_id and a dictionary of fields to update in the body.

For create_activity:
- Provide an activity_data dictionary for v2 Pipedrive API with at least:
  - 'deal_id' (the deal to attach the activity to, required)
  - 'subject' (required)
  - 'type' (required, e.g., call, meeting, task)
  - 'due_date' (string, e.g., '2024-06-01')
  - 'due_time' (string, e.g., '14:00' -- must be in 'HH:MM' 24-hour format, NOT 'HH:MM:SS')
  - 'done' (boolean: true for finished, false for scheduled)
  - 'note' (body/description)
- Uses POST /api/v2/activities. See Pipedrive v2 API docs for more details.

OUTPUT REQUIREMENTS:
- Always respond in strict JSON format as specified in the prompt
- Set "success" to true only if the request was fully satisfied
- Set "results_found" to true only if actual matching data was retrieved
- Include clear validation messages about data quality and any issues
- If user asks for a specific item that doesn't exist, mark as unsuccessful
- If the user explicitly requests to stop or exit if no results are found, set 'should_exit' to true in your output. Otherwise, issue a warning in the output and continue with the pipeline.
- If no results are found, this is NOT an error, but a valid result. Do NOT set error_message for this case; instead, set results_found: false and provide a data_summary or warning message explaining no results were found.

CONNECTION: {pipedrive}
CONTEXT: {context_json}"""

            model_id = config.get("ai_models", {}).get("default")

            ai_logger.action(
                f"Initiating AI agent with tool calling using model '{model_id}' for: {pipedrive_instructions[:100]}...",
                agent_id,
                account_id,
                agent_name,
            )
            logger.info(f"Starting Pipedrive agent with tool calling for: {pipedrive_instructions[:100]}...")

            # Use AI router in agent mode with the tools
            agent_result = await get_completion(
                prompt=prompt,
                model_id=model_id,
                agent_mode=True,
                tools=pipedrive_tools,
                system_message=system_message,
                verbose=True,
            )

            # Check if the agent result contains an error
            if agent_result.get("error"):
                ai_logger.error(f"AI agent execution failed: {agent_result.get('error')}", agent_id, account_id, agent_name)
                logger.error(f"Agent returned error for agent {agent_id}: {agent_result.get('error')}")
                raise Exception(agent_result.get("error"))

            total_steps = agent_result.get("total_steps", 0)
            ai_logger.result(f"AI agent completed successfully in {total_steps} steps", agent_id, account_id, agent_name)
            logger.info(f"Pipedrive agent completed {total_steps} steps for agent {agent_id}")

            # Parse the agent's JSON response for result quality
            ai_logger.action("Parsing and validating agent's JSON response for result quality", agent_id, account_id, agent_name)

            final_output = agent_result.get("final_output", "")
            parsed_result = extract_json_content(final_output)

            # If JSON extraction failed but we have output content, treat it as an error message
            if not parsed_result and final_output.strip():
                ai_logger.error(f"Failed to parse JSON from agent output: {final_output[:200]}...", agent_id, account_id, agent_name)
                logger.error(f"JSON parsing failed for agent {agent_id}, raw output: {final_output[:200]}...")
                raise Exception(f"Agent returned malformed response: {final_output}")

            # If we have no output at all
            if not parsed_result:
                ai_logger.error("Agent returned no output or empty response", agent_id, account_id, agent_name)
                logger.error(f"Agent {agent_id} returned no output")
                raise Exception("Agent returned no output")

            # Extract key result information
            results_found = parsed_result.get("results_found", False)
            data_summary = parsed_result.get("data_summary", "Data retrieved successfully")

            ai_logger.thinking(
                f"Results: results_found={results_found}, data_summary={data_summary}",
                agent_id,
                account_id,
                agent_name,
            )

            # No results found - check LLM output for should_exit flag
            if not results_found:
                should_exit = parsed_result.get("should_exit", False)
                if should_exit:
                    ai_logger.result("No matching results found for the Pipedrive request - agent will exit (LLM output should_exit=true)", agent_id, account_id, agent_name)
                    logger.info(f"No results found for Pipedrive request from agent {agent_id} (LLM output should_exit=true)")
                    return {"should_exit": True}
                else:
                    ai_logger.warning("No matching results found for the Pipedrive request - pipeline will continue (LLM output should_exit not set)", agent_id, account_id, agent_name)
                    logger.warning(f"No results found for Pipedrive request from agent {agent_id}, pipeline will continue (LLM output should_exit not set)")
                    return None

            # Results found - return the data
            result = parsed_result.get("pipedrive_data")

            ai_logger.result(f"Request fulfilled successfully: {data_summary}", agent_id, account_id, agent_name)
            logger.info(f"Pipedrive request fulfilled successfully for agent {agent_id}")

            return {"values": {"context": result, "output": result}}

    except Exception as e:
        ai_logger.error(f"Pipedrive agent execution failed: {str(e)}", agent_id, account_id, agent_name)
        logger.error(f"Pipedrive agent execution failed for agent {agent_id}: {str(e)}")
        raise
