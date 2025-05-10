"""
Research tools for agents.

This module provides tools for generating and managing research content.
"""

import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from ..core.ai_logger import ai_logger
from ..core.config import logger
from ..core.data_handler import DataHandler
from ..tools.base import tool
from ..utils.ai_router import get_completion
from ..utils.prompt_utils import get_prompt


@tool
async def research_perplexity(research_prompt: str, research_model: str, data_store: Dict[str, Any]):
    """
    Performs research using Perplexity.

    Args:
        research_prompt: The research prompt to process
        research_model: The model ID to use for research
        data_store: Agent's data store containing configuration and state

    Returns:
        Dictionary containing operation status and research results in values
    """
    assert research_prompt, "Research prompt must be provided"
    assert research_model, "Research model must be provided"
    assert data_store, "Data store must be provided"

    agent_id = data_store.get("agent_id")
    owner_id = data_store.get("owner_id")
    config = data_store.get("config", {})
    agent_name = config.get("name")
    assert owner_id, "owner_id must be provided in data_store config"
    
    today_date = datetime.utcnow().strftime("%Y-%m-%d")

    ai_logger.thinking(f"Starting research on: {research_prompt[:100]}...", agent_id=agent_id, owner_id=owner_id, agent_name=agent_name)

    # Format the prompt using XML style with nested context
    prompt_data = {
        "date": today_date,
        "task": "Conduct detailed and comprehensive research on the following research prompt.",
        "context": data_store.get("context", {}),
        "research_prompt": research_prompt,
    }
    prompt = get_prompt(prompt_data)
    
    ai_logger.action(f"Querying Perplexity with formatted prompt", agent_id=agent_id, owner_id=owner_id, agent_name=agent_name)
    research_result = await get_completion(prompt=prompt, model_id=research_model)
    
    ai_logger.result(f"Research completed successfully. Generated {len(research_result)} characters of insights", agent_id=agent_id, owner_id=owner_id, agent_name=agent_name)

    return {
        "status": "success",
        "message": "Perplexity research completed",
        "values": {"context": {"research": research_result}, "output": {"latest_research": research_result}},
    }


async def generate_daily_research(data_store: Dict[str, Any]):
    """
    Generates daily research content based on configured topics and sources,
    using a cache to avoid redundant generation.

    Checks the database for recent research for each topic. If found and recent
    (within the configured frequency), uses the cached version. Otherwise,
    generates new research and saves it to the database.

    Analyzes various data sources to compile comprehensive research insights
    for content creation and knowledge building.

    Args:
        data_store: Agent's data store containing configuration, state, and context

    Returns:
        Dictionary with operation status and values to be shared in data_store
    """
    assert data_store, "Data store must be provided"

    config = data_store.get("config", {})
    agent_id = data_store.get("agent_id")
    owner_id = config.get("owner_id") or config.get("account_holder_id")
    agent_name = config.get("name")
    assert owner_id, "owner_id must be provided in data_store config"

    daily_research_topics = config.get("daily_research_topics")
    assert daily_research_topics, "daily_research_topics must be configured"
    assert isinstance(daily_research_topics, dict), "daily_research_topics must be a dictionary"

    research_model_id = config.get("ai_models", {}).get("research")
    assert research_model_id, "Researching model ID must be configured in ai_models"

    handler = DataHandler(collection_name="research_cache")

    now = datetime.utcnow()

    today_date = now.strftime("%Y-%m-%d")
    run_frequency_days = config.get("research_run_frequency_days", 1)  # Allow config override

    research_outputs: Dict[str, Any] = {}
    tasks_to_run: Dict[str, asyncio.Task] = {}
    topics_to_generate = []

    ai_logger.thinking(f"Starting daily research check for {len(daily_research_topics)} topics", agent_id=agent_id, owner_id=owner_id, agent_name=agent_name)

    # 1. Prepare cache keys and fetch existing data in bulk
    potential_keys_map: Dict[str, str] = {}  # Map topic_key to cache_key
    potential_cache_keys: List[str] = []
    for topic_key, query in daily_research_topics.items():
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        cache_key = f"query_{query_hash}_{today_date}"
        potential_keys_map[topic_key] = cache_key
        potential_cache_keys.append(cache_key)

    cached_data_map: Dict[str, Dict[str, Any]] = {}
    try:
        if potential_cache_keys:
            # Fetch all potential cached items in one query for efficiency
            cached_data_map = await handler.get_data_by_keys(potential_cache_keys)
        logger.info(f"Checked cache for {len(potential_cache_keys)} potential topics, found {len(cached_data_map)} entries.")
    except Exception as e:
        logger.error(f"Error fetching bulk research from cache: {e}. Proceeding without cache.")
        # If bulk fetch fails, we can decide to proceed without cache or return an error
        # For now, log the error and continue, potentially regenerating everything

    # 2. Determine which topics need generation based on cache check
    for topic_key, query in daily_research_topics.items():
        research_key = potential_keys_map[topic_key]
        cached_data = cached_data_map.get(research_key)
        needs_update = True

        if cached_data:
            last_updated = cached_data.get("last_updated")
            # Assuming both are naive UTC for comparison
            if last_updated and (now - last_updated) <= timedelta(days=run_frequency_days):
                logger.info(f"Using cached research for topic: {topic_key} (key: {research_key})")
                research_outputs[topic_key] = cached_data.get("content")
                needs_update = False
            else:
                logger.info(f"Cached research for topic: {topic_key} is outdated or timestamp missing. Regenerating.")
        else:
            logger.info(f"No cached research found for topic: {topic_key} (key: {research_key}). Queueing generation.")

        if needs_update:
            topics_to_generate.append(topic_key)

            # Format the prompt using XML style with nested context
            prompt_data = {
                "date": today_date,
                "task": "Provide today's comprehensive update on the following topic. Focus on the latest information, key developments, and the current situation.",
                "topic_query": query,
                "output_format": "Detailed text response, focusing on information relevant as of today.",
                "context": data_store.get("context", {}),
            }

            prompt = get_prompt(prompt_data, "research_request")

            tasks_to_run[topic_key] = asyncio.create_task(
                get_completion(prompt=prompt, model_id=research_model_id),
                name=f"research_{topic_key}",
            )

    # 3. Run generation tasks concurrently if any are needed
    if tasks_to_run:
        ai_logger.action(f"Generating research for {len(tasks_to_run)} topics", agent_id=agent_id, owner_id=owner_id, agent_name=agent_name)
        try:
            results_list = await asyncio.gather(*tasks_to_run.values())
            new_results = dict(zip(tasks_to_run.keys(), results_list))

            # 4. Save new results to cache and update output dictionary
            save_tasks = []
            generation_errors = False
            for topic_key, result in new_results.items():
                if isinstance(result, Exception):
                    ai_logger.result(f"Research generation failed for topic {topic_key}: {result}", agent_id=agent_id, owner_id=owner_id, agent_name=agent_name)
                    generation_errors = True
                    break
                else:
                    research_outputs[topic_key] = result
                    research_key = potential_keys_map[topic_key]
                    save_tasks.append(handler.save_data(research_key, result, now))

            if generation_errors:
                return {"status": "error", "message": "Research generation failed for one or more topics", "values": {}}

            if save_tasks:
                try:
                    save_results = await asyncio.gather(*save_tasks)
                    if not all(save_results):
                        ai_logger.result("One or more save operations failed", agent_id=agent_id, owner_id=owner_id, agent_name=agent_name)
                        return {"status": "error", "message": "Failed to save one or more research topics", "values": {}}
                except Exception as e:
                    ai_logger.result(f"Error saving research data: {e}", agent_id=agent_id, owner_id=owner_id, agent_name=agent_name)
                    return {"status": "error", "message": f"Error saving research data: {e}", "values": {}}

        except Exception as e:
            ai_logger.result(f"Error during parallel research generation: {e}", agent_id=agent_id, owner_id=owner_id, agent_name=agent_name)
            return {"status": "error", "message": f"Error during research generation: {e}", "values": {}}

    generated_count = len(tasks_to_run)
    cached_count = len(daily_research_topics) - generated_count
    message = f"Research complete. Generated: {generated_count}, Cached: {cached_count}."
    ai_logger.result(message, agent_id=agent_id, owner_id=owner_id, agent_name=agent_name)

    return {"status": "success", "message": message, "values": {"daily_research_results": research_outputs}}


async def research_topic(data_store: Dict[str, Any], topic: Optional[Union[str, Dict[str, Any]]] = None):
    """
    Performs detailed research on a specified topic.

    Uses the provided 'topic' argument if available. If 'topic' is None,
    it falls back to using 'selected_topic' from the data_store.
    The topic can be a string (query) or a dictionary containing details.
    Generates content suitable for detailed posts or tweets.

    Args:
        data_store: Agent's data store containing configuration ('config')
                    and optionally 'selected_topic' if 'topic' arg is None.
        topic: The topic to research (optional). Can be a string or a dictionary.
               If None, 'selected_topic' from data_store is used.

    Returns:
        Dictionary with operation status and the research result in values.
    """
    assert data_store, "Data store must be provided"

    config = data_store.get("config", {})
    agent_id = data_store.get("agent_id")
    owner_id = config.get("owner_id") or config.get("account_holder_id")
    agent_name = config.get("name")
    assert owner_id, "owner_id must be provided in data_store config"

    # 1. Determine the actual topic to research
    actual_topic: Union[str, Dict[str, Any]]
    if topic is not None:
        actual_topic = topic
        ai_logger.thinking("Using provided topic argument for research", agent_id=agent_id, owner_id=owner_id, agent_name=agent_name)
    else:
        selected_topic = data_store.get("selected_topic")
        assert selected_topic, "Topic argument not provided and selected_topic not found in data_store"
        actual_topic = selected_topic
        ai_logger.thinking("Using selected_topic from data_store for research", agent_id=agent_id, owner_id=owner_id, agent_name=agent_name)

    assert isinstance(actual_topic, (str, dict)), "Resolved topic must be a string or a dictionary"

    # 2. Get required config
    research_model_id = config.get("ai_models", {}).get("research")
    assert research_model_id, "Researching model ID must be configured in ai_models"

    # 3. Construct the prompt using XML style with nested context
    today_date = datetime.utcnow().strftime("%Y-%m-%d")

    prompt_data = {
        "date": today_date,
        "task": """Conduct detailed and comprehensive research on the following specific topic, provided below in the topic_details section.
Expand on the provided details, find the latest developments, related news, background information,
and provide in-depth analysis suitable for creating informative content (e.g., a detailed tweet thread or blog post section).
Focus on accuracy, depth, and relevance as of today. Structure the output clearly.""",
        "topic_details": str(actual_topic),
        "context": data_store.get("context", {}),
        "outputs": data_store.get("outputs", {}),
    }

    prompt = get_prompt(prompt_data, "research_request")

    ai_logger.action("Calling AI model for detailed research", agent_id=agent_id, owner_id=owner_id, agent_name=agent_name)

    try:
        research_result = await get_completion(prompt=prompt, model_id=research_model_id)
        ai_logger.result("Successfully completed detailed research for the topic", agent_id=agent_id, owner_id=owner_id, agent_name=agent_name)
        return {"status": "success", "message": "Detailed research completed for the topic.", "values": {"context": research_result}}

    except Exception as e:
        ai_logger.result(f"Error during detailed research: {e}", agent_id=agent_id, owner_id=owner_id, agent_name=agent_name)
        return {"status": "error", "message": f"Error during detailed research for the topic: {e}", "values": {}}
