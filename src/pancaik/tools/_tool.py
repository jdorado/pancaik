"""
Sample tool skeleton for Pancaik agents.

This module provides a template for creating new tools using the @tool decorator.

# - Tool is always async, no nested functions, keep it simple
# - Return {values: {context: {new_key: new_value}}} and use descriptive, globally-unique keys
# - Add 'should_exit': True to the return dict to gracefully end the pipeline when needed
# - Add 'should_process': True and 'process_minutes': X to enter processing mode and resume from next step
# - Use a proper name to identify the output in a global context (avoid ambiguous names)
# - Do NOT use try/catch in the tool (the @tool decorator handles exceptions)
# - Follow the sample code pattern and keep code modular, clear, and open source quality

## Return Structure Guidelines:
# ONLY return 'values' when you have meaningful data to add:
# - 'context': Only include if you have new/updated context data to store
# - 'output': Only include if you have meaningful output data to return
#
# Clean return patterns:
# 1. Success with data: {"values": {"context": {...}, "output": {...}}}
# 2. Success with only context: {"values": {"context": {...}}}
# 3. Success with only output: {"values": {"output": {...}}}
# 4. Graceful exit (no data): {"should_exit": True}
# 5. Processing mode: {"should_process": True, "process_minutes": X, "values": {...}} (only if you have data)
#
# DON'T return empty/meaningless values just to have something - keep it clean!
#
# Examples of GOOD returns:
# return {"values": {"context": {"user_id": "123", "status": "verified"}}}  # Only context
# return {"values": {"output": {"result": "success", "data": [...]}}}       # Only output
# return {"should_exit": True}                                              # Clean exit
#
# Examples of BAD returns (avoid these):
# return {"values": {"context": {}, "output": {}}}                         # Empty values
# return {"values": {"context": {"status": "ok"}, "output": {"status": "ok"}}}  # Redundant
# return {"should_exit": True, "values": {"context": {}}}                  # Unnecessary empty values

## Error Handling:
# - For hard failures that should stop execution: raise Exception("error message")
# - For graceful exits (user config issues, etc.): return {"should_exit": True}
# - When using should_exit: True, no need to return values - just {"should_exit": True} is enough

## Error Handling Pattern:
# Two options for handling errors in tools:
# 1. HARD FAILURE (must fail): Raise an exception - the @tool decorator will handle it
# 2. GRACEFUL EXIT: Return {"should_exit": True}
#    - Use this when the error is expected/recoverable and you want to end the pipeline gracefully
#    - Only add values if you have meaningful error context to preserve
#    - Don't return complex error objects or empty data just to fill the structure

## Processing Mode Feature Usage:

When a tool returns 'should_process': True, the agent will:
1. Save current state (context, outputs, and other data_store items)
2. Schedule resumption after 'process_minutes' (default: 10)
3. Agent status remains "scheduled" but with resume_from_step set (indicating processing mode)
4. Resume execution from the current step in the pipeline
5. Restore all saved state (context, outputs, data_store)
6. Continue with remaining steps
7. Clear all resume info when pipeline completes or fails permanently

State Preservation:
- All context items with their metadata are saved and restored
- All outputs with their metadata are saved and restored
- Other data_store items are preserved across processing mode
- The restored state is available to subsequent tools

Example scenarios:
- Making async API calls that need time to process
- Waiting for external systems to respond
- Rate limiting / throttling
- Waiting for user interactions to complete

Example: Agent with tools [A, B, C, D]
- Step A completes normally, adds context: {"step_a_result": "value1"}
- Step B returns should_process=True, process_minutes=15, adds context: {"step_b_result": "value2"}
- Agent enters processing mode, saves ALL context and outputs to database
- Agent resumes after 15 minutes and re-executes Step B (current step)
- Step B can check if processing completed and proceed, or continue processing
- Steps C and D execute normally with full context available
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..core.config import logger
from ..utils.ai_router import get_completion
from ..utils.json_parser import extract_json_content
from ..utils.prompt_utils import get_prompt
from .base import tool


# Example: Register this tool for a specific agent by passing agents=["agent_example"]
@tool()  # leave like this no extras
async def sample_tool(
    data_store: Dict[str, Any], sample_param: str = "default_value", resuming_from_step: Optional[str] = None, is_resuming: bool = False
) -> Dict[str, Any]:
    """
    Sample tool demonstrating the basic pattern for Pancaik tools.

    This tool shows how to:
    - Access data_store for context and configuration
    - Use AI completion for processing
    - Return structured data with context and output
    - Control pipeline flow with should_exit and should_suspend flags

    Args:
        data_store: Agent's data store containing context, config, etc.
        sample_param: Example parameter with default value
        resuming_from_step: Name of the step being resumed from (if resuming)
        is_resuming: Whether this tool is being resumed from processing mode

    Returns:
        Dictionary with tool results and optional flow control flags
    """
    # Extract common context for logging and AI operations
    agent_id = data_store.get("agent_id")
    config = data_store.get("config", {})
    agent_name = config.get("name", "unknown")

    logger.info(f"Running sample_tool for agent {agent_id} ({agent_name})")

    # Check if resuming from this step
    if is_resuming and resuming_from_step == "sample_tool":
        logger.info(f"Resuming sample_tool - checking if processing completed")

        # Example: Check if our processing is done
        processing_completed = True  # Replace with actual status check

        if not processing_completed:
            # Still processing, continue waiting
            return {
                "should_process": True,
                "process_minutes": 5,
                "values": {
                    "context": {"sample_tool_status": "still_processing", "check_timestamp": datetime.now(timezone.utc).isoformat()}
                },
            }
        else:
            # Processing completed, return results
            return {
                "values": {
                    "context": {"sample_tool_status": "completed", "completion_timestamp": datetime.now(timezone.utc).isoformat()},
                    "output": {"processing_completed": True, "status": "success"},
                }
            }

    # Example: Access agent context
    context = data_store.get("context", {})

    # Example: Use AI for processing
    prompt_data = {"task": f"Process the sample parameter: {sample_param}", "context": context, "agent_name": agent_name}

    prompt = get_prompt(prompt_data)
    model_id = config.get("ai_models", {}).get("default")
    response = await get_completion(prompt=prompt, model_id=model_id)

    # Parse AI response
    processed_result = extract_json_content(response) or {"result": response}

    # Example conditional flow control based on your business logic
    should_process_execution = sample_param == "process_test"  # Example condition
    should_exit_pipeline = sample_param == "exit_test"  # Example condition

    # Example: Exit pipeline early if condition is met (clean exit - no unnecessary data)
    if should_exit_pipeline:
        logger.info(f"sample_tool for agent {agent_id}: Exiting pipeline early")
        return {"should_exit": True}

    # Example: Enter processing mode (only return values if you have meaningful data)
    elif should_process_execution:
        logger.info(f"sample_tool for agent {agent_id}: Entering processing mode for 15 minutes")
        return {
            "should_process": True,
            "process_minutes": 15,
            "values": {
                "context": {"sample_tool_status": "processing_started", "process_timestamp": datetime.now(timezone.utc).isoformat()}
            },
        }

    # Normal completion with meaningful data to return
    context_updates = {"sample_tool_result": processed_result, "sample_param_processed": sample_param, "last_tool_execution": "sample_tool"}

    output_data = {"tool_name": "sample_tool", "processed_data": processed_result, "status": "completed"}

    return {"values": {"context": context_updates, "output": output_data}}


@tool()
async def processing_demo_tool(
    data_store: Dict[str, Any], action: str = "prepare", process_minutes: int = 1  # "prepare" or "check"
) -> Dict[str, Any]:
    """
    Demonstration tool showing how state is preserved across processing mode.

    Use action="prepare" to add context and enter processing mode.
    Use action="check" to verify the context was preserved.

    Args:
        data_store: Agent's data store
        action: Either "prepare" (adds context + enters processing mode) or "check" (verifies context)
        process_minutes: Minutes to wait in processing mode if action="prepare"

    Returns:
        Dictionary with results and optional processing flag
    """
    agent_id = data_store.get("agent_id")
    context = data_store.get("context", {})

    if action == "prepare":
        # Add some context that should be preserved
        context_updates = {
            "processing_demo_timestamp": datetime.now(timezone.utc).isoformat(),
            "processing_demo_data": "This data should survive processing mode",
            "processing_demo_counter": context.get("processing_demo_counter", 0) + 1,
        }

        result = {
            "should_process": True,
            "process_minutes": process_minutes,
            "values": {
                "context": context_updates,
                "output": {"action": "prepared_for_processing", "context_added": list(context_updates.keys())},
            },
        }

        logger.info(f"Agent {agent_id}: Prepared context for processing mode - will process for {process_minutes} minutes")

    elif action == "check":
        # Check if the context was preserved
        demo_timestamp = context.get("processing_demo_timestamp")
        demo_data = context.get("processing_demo_data")
        demo_counter = context.get("processing_demo_counter", 0)

        preserved = demo_timestamp is not None and demo_data is not None

        result = {
            "values": {
                "context": {"processing_demo_verified": preserved, "verification_timestamp": datetime.now(timezone.utc).isoformat()},
                "output": {
                    "action": "verified_processing_state",
                    "context_preserved": preserved,
                    "demo_timestamp": demo_timestamp,
                    "demo_data": demo_data,
                    "demo_counter": demo_counter,
                    "status": "success" if preserved else "failed",
                },
            }
        }

        if preserved:
            logger.info(f"Agent {agent_id}: ✅ Context was preserved across processing mode!")
        else:
            logger.warning(f"Agent {agent_id}: ❌ Context was NOT preserved across processing mode")

    else:
        raise ValueError(f"Invalid action '{action}'. Must be 'prepare' or 'check'")

    return result
