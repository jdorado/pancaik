"""
Email handler module for external agent triggering via email.

This module provides functionality to securely execute agents via email requests
with token-based authentication and email context injection.
"""

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import HTTPException

from ..tools.base import tool
from .agent import Agent
from .agent_handler import AgentHandler
from .config import get_config, logger


@tool
async def email_trigger(agent_id: str, token: str = "", email_data: Dict[str, Any] = {}) -> Dict[str, Any]:
    """
    Execute an agent via email with token authentication and email context injection.

    Args:
        agent_id: The ID of the agent to execute (extracted from email address)
        token: The bearer token for authentication (injected during call)
        email_data: Dictionary containing email data (id, to, from, subject, body) (injected during call)

    Returns:
        Dictionary containing execution result

    Raises:
        HTTPException: If authentication fails or agent execution errors occur
    """
    # Preconditions
    assert isinstance(agent_id, str), "Agent ID must be a string"
    assert isinstance(token, str), "Token must be a string"
    assert isinstance(email_data, dict), "Email data must be a dictionary"

    logger.info(f"Email trigger requested for agent {agent_id}")

    try:
        # Get the agent from database first
        agent_doc = await AgentHandler.get_agent(agent_id)
        if not agent_doc:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        # Check if agent is active
        if not agent_doc.get("is_active", True):
            raise HTTPException(status_code=400, detail=f"Agent {agent_id} is not active")

        # Check if the agent has email trigger enabled
        email_trigger_found = False
        triggers = agent_doc.get("triggers", [])
        for trigger in triggers:
            if trigger.get("id") == "email_trigger":
                email_trigger_found = True
                break

        if not email_trigger_found:
            logger.warning(f"No email trigger configured for agent {agent_id}")
            raise HTTPException(status_code=403, detail="No email trigger configured for this agent")

        # Verify email token against system-wide email token from config
        system_email_token = get_config("email_token")

        if not system_email_token:
            logger.warning("No system email token configured")
            raise HTTPException(status_code=403, detail="No system email token configured")

        if token != system_email_token:
            logger.warning(f"Invalid email token provided for agent {agent_id}")
            raise HTTPException(status_code=403, detail="Invalid email token")

        logger.info(f"Email token verified for agent {agent_id}")

        # Create Agent instance
        agent = Agent(id=agent_id, config=agent_doc)

        # Inject email data into the agent's data store
        if email_data:
            # Add metadata for email-injected context
            current_time = datetime.now(timezone.utc)
            
            # Structure the email data for better agent consumption
            structured_email_data = {
                "email_from": email_data.get("from", ""),
                "email_subject": email_data.get("subject", ""),
                "email_body": email_data.get("body", ""),
            }
            
            agent.data_store["context"]["email_received"] = {
                "value": structured_email_data,
                "tool_id": "email_trigger",
                "phase": "trigger",
                "created_at": current_time,
            }
            logger.info(f"Injected email context into agent {agent_id}: from={email_data.get('from')}")

        # Execute the agent task
        logger.info(f"Executing email-triggered agent {agent_id}")
        await agent.execute(no_retry=True)

        # Get the final outputs from the agent
        outputs = agent.get_ordered_outputs()

        return {
            "status": "success",
            "message": f"Agent {agent_id} executed successfully via email",
            "agent_id": agent_id,
            "execution_time": datetime.now(timezone.utc).isoformat(),
            "email_from": email_data.get("from", ""),
            "email_subject": email_data.get("subject", ""),
            "outputs_count": len(outputs),
            "outputs": outputs,
        }

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Email execution failed for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}") 