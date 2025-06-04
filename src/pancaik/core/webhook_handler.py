"""
Webhook handler module for external agent triggering.

This module provides functionality to securely execute agents via webhook requests
with token-based authentication and context injection.
"""

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import HTTPException

from .agent import Agent
from .agent_handler import AgentHandler
from .config import logger
from .task_runner import execute_task
from ..tools.base import tool


@tool
async def webhook(agent_id: str, token: str, context_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute an agent via webhook with token authentication and context injection.
    
    Args:
        agent_id: The ID of the agent to execute
        token: The bearer token for authentication
        context_data: Dictionary of context data to inject into the agent
        
    Returns:
        Dictionary containing execution result
        
    Raises:
        HTTPException: If authentication fails or agent execution errors occur
    """
    # Preconditions
    assert isinstance(agent_id, str), "Agent ID must be a string"
    assert isinstance(token, str), "Token must be a string"
    assert isinstance(context_data, dict), "Context data must be a dictionary"
    
    logger.info(f"Webhook trigger requested for agent {agent_id}")
    
    try:
        # Get the agent from database first
        agent_doc = await AgentHandler.get_agent(agent_id)
        if not agent_doc:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        
        # Check if agent is active
        if not agent_doc.get("is_active", True):
            raise HTTPException(status_code=400, detail=f"Agent {agent_id} is not active")
        
        # Verify webhook token against agent's stored token
        stored_webhook_token = None
        
        # Extract webhook token from triggers array
        triggers = agent_doc.get("triggers", [])
        for trigger in triggers:
            if trigger.get("id") == "webhook":
                params = trigger.get("params", {})
                stored_webhook_token = params.get("webhook_token")
                break
        
        if not stored_webhook_token:
            logger.warning(f"No webhook token configured for agent {agent_id}")
            raise HTTPException(status_code=403, detail="No webhook token configured for this agent")
        
        if token != stored_webhook_token:
            logger.warning(f"Invalid webhook token provided for agent {agent_id}")
            raise HTTPException(status_code=403, detail="Invalid webhook token for this agent")
        
        logger.info(f"Webhook token verified for agent {agent_id}")
        
        # Create Agent instance
        agent = Agent(id=agent_id, config=agent_doc)
        
        # Inject context data into the agent's data store
        if context_data:
            # Add metadata for webhook-injected context
            current_time = datetime.now(timezone.utc)
            for key, value in context_data.items():
                agent.data_store["context"][key] = {
                    "value": value,
                    "tool_id": "webhook_trigger",
                    "phase": "trigger",
                    "created_at": current_time,
                }
            logger.info(f"Injected {len(context_data)} context variables into agent {agent_id}")
        
        # Execute the agent task
        logger.info(f"Executing webhook-triggered agent {agent_id}")
        await execute_task(agent)
        
        # Get the final outputs from the agent
        outputs = agent.get_ordered_outputs()
        
        return {
            "status": "success",
            "message": f"Agent {agent_id} executed successfully via webhook",
            "agent_id": agent_id,
            "execution_time": datetime.now(timezone.utc).isoformat(),
            "context_injected": list(context_data.keys()) if context_data else [],
            "outputs_count": len(outputs),
            "outputs": outputs
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Webhook execution failed for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}") 