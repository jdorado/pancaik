"""
HubSpot CRM Agent Tool

This module provides an AI-powered agent that uses tool calling to interact with HubSpot CRM.
The agent receives instructions and context, then uses LLM tool calling to execute specific
HubSpot API functions directly. This allows for more precise and flexible CRM operations.
"""

import datetime
import json
from typing import Any, Dict

from ...core.ai_logger import ai_logger
from ...core.config import get_config, logger
from ...core.connections import ConnectionHandler
from ...tools.base import tool
from ...utils.ai_router import get_completion
from ...utils.json_parser import extract_json_content
from ...utils.prompt_utils import get_prompt
from .hubspot_cache import load_and_cache_hubspot_metadata, simplify_hubspot_metadata
from .hubspot_client import HubspotClient

OUTPUT_FORMAT = """OUTPUT IN JSON: Strict JSON format, no additional text.\\n{
"
    "    \"success\": boolean,\\n"
    "    \"results_found\": boolean,  // true if any matching data was found, false if not\\n"
    "    \"data_summary\": \"string summary of data retrieved or why no results\",\\n"
    "    \"should_exit\": boolean,  // true if user explicitly requested to stop if no results, else false or omitted\\n"
    "    \"hubspot_data\": \"relevant hubspot data or null\"\\n"
    "}"""


@tool()
async def hubspot_agent(data_store: Dict[str, Any], hubspot: str, hubspot_instructions: str) -> Dict[str, Any]:
    """
    AI-powered HubSpot CRM agent that uses tool calling to execute CRM operations.

    This agent receives natural language instructions and uses LLM tool calling to execute
    specific HubSpot API functions. The LLM will have access to HubSpot tools and can
    call them directly based on the instructions and context.

    Args:
        data_store: Agent's data store containing context, config, etc.
        hubspot: HubSpot connection ID
        hubspot_instructions: Natural language instructions for CRM operations

    Returns:
        Dictionary with tool calling results and context updates
    """
    # Extract common context for logging and AI operations
    agent_id = data_store.get("agent_id")
    config = data_store.get("config", {})
    agent_name = config.get("name", "hubspot_agent")
    account_id = config.get("account_id")
    context = data_store.get("context", {})

    # AI logging for initial analysis
    ai_logger.thinking(
        f"Starting HubSpot CRM agent analysis for instructions with connection ID: {hubspot}",
        agent_id,
        account_id,
        agent_name,
    )

    logger.info(f"Running HubSpot CRM agent for agent {agent_id} ({agent_name})")

    # Validate HubSpot connection ID
    if not hubspot:
        ai_logger.error("No HubSpot connection ID provided - cannot proceed with CRM operations", agent_id, account_id, agent_name)
        logger.error(f"HubSpot connection ID not provided for agent {agent_id}")
        return {"should_exit": True}

    # Get database instance from config
    db = get_config("db")
    if db is None:
        ai_logger.error("Database not initialized - cannot access HubSpot connections", agent_id, account_id, agent_name)
        raise ValueError("Database not initialized in config")

    # Initialize connection handler with db
    connection_handler = ConnectionHandler(db)

    ai_logger.action(f"Retrieving HubSpot connection details for connection ID: {hubspot}", agent_id, account_id, agent_name)

    # Get the connection parameters
    connection_params = await connection_handler.get_connection(hubspot)
    if not connection_params:
        ai_logger.error(
            f"HubSpot connection '{hubspot}' not found in database - please verify connection exists", agent_id, account_id, agent_name
        )
        raise ValueError(f"HubSpot connection not found: {hubspot}")

    # Get API token from connection parameters
    access_token = connection_params.get("access_token")
    if not access_token:
        ai_logger.error(
            "No access token found in HubSpot connection parameters - authentication will fail", agent_id, account_id, agent_name
        )
        raise ValueError("Access token not found in HubSpot connection parameters")

    ai_logger.result("Successfully retrieved HubSpot connection with access token", agent_id, account_id, agent_name)
    logger.info(f"Retrieved HubSpot connection for agent {agent_id}")

    # Load and cache essential HubSpot metadata (deal pipelines, stages)
    ai_logger.action("Loading HubSpot metadata (deal pipelines, stages) from cache or API", agent_id, account_id, agent_name)

    try:
        cached_metadata = await load_and_cache_hubspot_metadata(
            connection_handler=connection_handler,
            connection_id=hubspot,
            force_refresh=False,  # Use cached data if available and valid
            cache_expiry_days=7,  # Cache expires after 1 week
        )

        metadata_summary = [f"{k}: {len(v) if isinstance(v, list) else 1}" for k, v in cached_metadata.items()]
        ai_logger.result(f"Successfully loaded HubSpot metadata: {', '.join(metadata_summary)}", agent_id, account_id, agent_name)

        logger.info(f"HubSpot metadata loaded for connection {hubspot}")
        logger.debug(f"Cached items: {metadata_summary}")
    except Exception as cache_error:
        ai_logger.warning(
            f"Failed to load HubSpot metadata cache: {str(cache_error)} - proceeding with limited context",
            agent_id,
            account_id,
            agent_name,
        )
        logger.warning(f"Failed to load HubSpot metadata cache: {str(cache_error)}")
        cached_metadata = {}

    # Simplify cached metadata structure for the LLM
    simplified_metadata = simplify_hubspot_metadata(cached_metadata)

    # Add current UTC datetime to context for LLM awareness
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    context["current_utc_datetime"] = now_utc.isoformat()

    ai_logger.thinking(
        f"Prepared simplified metadata context for LLM with {len(simplified_metadata)} metadata categories",
        agent_id,
        account_id,
        agent_name,
    )

    try:
        # Initialize HubSpot client
        ai_logger.action("Initializing HubSpot client and creating tool calling capabilities", agent_id, account_id, agent_name)

        hubspot_client = HubspotClient.create(connection_id=hubspot, connection_handler=connection_handler)
        
        # Create LangChain tools from the client methods
        try:
            hubspot_tools = hubspot_client.create_tools()
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
            "instructions": hubspot_instructions,
            "context": context,
            "hubspot_metadata": simplified_metadata,
            "available_tools": [
                "get_deals - Get a list of deals from HubSpot.",
                "get_deal - Get a specific deal by ID. Use 'associations' to fetch related contacts or companies.",
                "search_deals - Search for deals using a query. Use this for filtering.",
                "get_contacts - Get a list of contacts from HubSpot.",
                "get_contact - Get a specific contact by ID. Use 'associations' to fetch related deals or companies.",
                "search_contacts - Search for contacts using a query. Use this for filtering.",
                "get_companies - Get a list of companies from HubSpot.",
                "create_deal - Create a new deal in HubSpot.",
                "update_deal - Update an existing deal in HubSpot.",
                "create_contact - Create a new contact in HubSpot.",
                "update_contact - Update an existing contact in HubSpot.",
                "create_company - Create a new company in HubSpot.",
                "update_company - Update an existing company in HubSpot.",
            ],
            "output_format": OUTPUT_FORMAT,
        }

        prompt = get_prompt(prompt_data)

        # Create system message for the agent
        metadata_json = json.dumps(simplified_metadata, indent=2).replace("{", "{{").replace("}", "}}")
        context_json = json.dumps(context, indent=2).replace("{", "{{").replace("}", "}}") if context else "No additional context"

        system_message = f"""You are an expert HubSpot CRM assistant for {agent_name}.

AVAILABLE TOOLS:
- get_deals: Retrieve all deals.
- get_deal: Retrieve a single deal by ID. Can retrieve associated objects like contacts.
- search_deals: Search for deals with a query.
- get_contacts: Retrieve all contacts.
- get_contact: Retrieve a single contact by ID. Can retrieve associated objects like deals.
- search_contacts: Search for contacts with a query.
- get_companies: Retrieve companies from HubSpot.
- create_deal: Create a new deal.
- update_deal: Update an existing deal.
- create_contact: Create a new contact.
- update_contact: Update an existing contact.
- create_company: Create a new company.
- update_company: Update an existing company.

HUBSPOT METADATA CONTEXT:
{metadata_json}

INSTRUCTIONS:
1. Use the available tools to gather information and perform actions.
2. Analyze the user's request to determine the correct tool and parameters.
3. To find contacts for a specific deal, first get the deal using `get_deal` and pass `associations=["contacts"]`. The result will contain associated contact IDs. Then, you can fetch contact details using `get_contact` for each ID.
4. Use the `search_deals` or `search_contacts` tools when you need to filter by properties.
5. Use the metadata to find correct IDs for pipelines and stages when creating or updating deals.
6. Provide clear error messages if data cannot be found or a request is invalid.
7. If the user asks to stop if no results are found, set 'should_exit' to true.
8. If no results are found, it is a valid result. Set 'results_found' to false and explain in the summary.

PARAMETER USAGE:
- For `get_deal` and `get_contact`, you can use `associations=["contacts"]` or `associations=["companies"]` to get associated object IDs.
- For `search_deals` and `search_contacts`, use the `query` parameter to filter. For example, to find a contact with a specific email, you can use `search_contacts(query="email@example.com")`.

OUTPUT REQUIREMENTS:
- Respond in strict JSON format.
- "success" should be true only if the request was fully satisfied.
- "results_found" should be true only if matching data was retrieved.
- If a specific item is not found, mark as unsuccessful.

CONNECTION: {hubspot}
CONTEXT: {context_json}"""

        model_id = "anthropic/claude-sonnet-4"

        # Use AI router in agent mode with the tools
        agent_result = await get_completion(
            prompt=prompt,
            model_id=model_id,
            agent_mode=True,
            tools=hubspot_tools,
            system_message=system_message,
            verbose=True,
        )

        if agent_result.get("error"):
            ai_logger.error(f"AI agent execution failed: {agent_result.get('error')}", agent_id, account_id, agent_name)
            logger.error(f"Agent returned error for agent {agent_id}: {agent_result.get('error')}")
            raise Exception(agent_result.get("error"))

        total_steps = agent_result.get("total_steps", 0)
        ai_logger.result(f"AI agent completed successfully in {total_steps} steps", agent_id, account_id, agent_name)
        logger.info(f"HubSpot agent completed {total_steps} steps for agent {agent_id}")

        ai_logger.action("Parsing and validating agent's JSON response", agent_id, account_id, agent_name)

        final_output = agent_result.get("final_output", "")
        parsed_result = extract_json_content(final_output)

        if not parsed_result:
            raise ValueError(f"Agent returned malformed JSON: {final_output}")

        results_found = parsed_result.get("results_found", False)
        data_summary = parsed_result.get("data_summary", "Data retrieved successfully")

        ai_logger.thinking(
            f"Results: results_found={results_found}, data_summary={data_summary}",
            agent_id,
            account_id,
            agent_name,
        )

        if not results_found:
            should_exit = parsed_result.get("should_exit", False)
            if should_exit:
                ai_logger.result(
                    "No matching results found for the HubSpot request - agent will exit",
                    agent_id,
                    account_id,
                    agent_name,
                )
                logger.info(f"No results found for HubSpot request from agent {agent_id}, exiting.")
                return {"should_exit": True}
            else:
                ai_logger.warning(
                    "No matching results found for the HubSpot request - pipeline will continue",
                    agent_id,
                    account_id,
                    agent_name,
                )
                logger.warning(
                    f"No results found for HubSpot request from agent {agent_id}, continuing."
                )
                return None

        result = parsed_result.get("hubspot_data")

        ai_logger.result(f"Request fulfilled successfully: {data_summary}", agent_id, account_id, agent_name)
        logger.info(f"HubSpot request fulfilled successfully for agent {agent_id}")

        ai_logger.result("Successfully parsed agent's JSON response", agent_id, account_id, agent_name)

        return {"values": {"context": result, "output": result}}

    except Exception as e:
        ai_logger.error(f"HubSpot agent failed with unhandled exception: {str(e)}", agent_id, account_id, agent_name)
        logger.error(f"HubSpot agent failed for agent {agent_id}", exc_info=True)
        return {"should_exit": True, "error": str(e)}
    finally:
        if "hubspot_client" in locals() and hubspot_client:
            hubspot_client.close()