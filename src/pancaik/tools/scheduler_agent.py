from datetime import datetime, timezone
from typing import Any, Dict
from .base import tool
from ..core.config import logger
from ..utils.ai_router import get_completion
from ..utils.json_parser import extract_json_content
from .scheduler import convert_to_datetime
from ..utils.prompt_utils import get_prompt
from ..core.ai_logger import ai_logger

@tool()
async def scheduler_agent(
    data_store: Dict[str, Any],
    schedule_instructions: str,
) -> Dict[str, Any]:
    """
    Parse natural language scheduling instructions and return the next run datetime (UTC).
    Args:
        data_store: Agent's data store containing configuration and state
        schedule_instructions: Natural language instructions for the schedule.
    Returns:
        Dictionary with 'success' and 'next_run' (datetime or None if error)
    """
    agent_id = data_store.get("agent_id")
    config = data_store.get("config", {})
    account_id = config.get("account_id")
    agent_name = config.get("name")
    ai_logger.thinking("Interpreting schedule instructions", agent_id, account_id, agent_name)
    logger.info(f"[scheduler_agent] Interpreting schedule for agent {agent_id}")
    now_utc = datetime.now(timezone.utc)

    # Compose a structured prompt for the LLM
    prompt_data = {
        "instructions": schedule_instructions,
        "current_utc_time": now_utc.isoformat(),
        "output_format": (
            'OUTPUT IN STRICT JSON: {"next_run": "<ISO8601 datetime in UTC>", "reason": "<short explanation of why this matches the pattern>"}.'
            ' If the instructions are ambiguous or invalid, return {"error": "Could not determine next run datetime", "reason": "<short explanation of why parsing failed or was ambiguous>"}.'
        ),
    }
    prompt = get_prompt(prompt_data)
    model_id = config.get("ai_models", {}).get("default")
    response = await get_completion(
        prompt=prompt,
        model_id=model_id,
        temperature=0.0,
    )

    parsed = extract_json_content(response) or {"error": "Failed to parse datetime", "raw_response": response, "reason": "Could not extract JSON from response"}

    # Try to convert the next_run to a datetime object (if present)
    next_run_dt = None
    success = False
    reason = parsed.get("reason")
    if "next_run" in parsed:
        try:
            next_run_dt = convert_to_datetime(parsed["next_run"], "next_run")
            success = True
            ai_logger.result("Successfully parsed next run datetime", agent_id, account_id, agent_name)
        except Exception as e:
            logger.warning(f"[scheduler_agent] Invalid datetime: {e}")
            ai_logger.warning(f"Invalid datetime returned: {e}", agent_id, account_id, agent_name)
            parsed = {"error": f"Invalid datetime: {e}", "raw_response": response, "reason": reason or str(e)}
    elif "error" in parsed:
        ai_logger.error(f"Schedule parsing failed: {parsed.get('reason', 'Unknown error')}", agent_id, account_id, agent_name)
    else:
        ai_logger.warning("Schedule parsing returned ambiguous or incomplete result", agent_id, account_id, agent_name)

    return {"success": success, "next_run": next_run_dt} 