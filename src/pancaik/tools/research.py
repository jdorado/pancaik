"""
Research tools for agents.

This module provides tools for generating and managing research content.
"""

import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from ..core.config import logger
from ..core.data_handler import DataHandler
from ..tools.base import tool
from ..utils.ai_router import get_completion


@tool
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

    logger.info(f"Starting daily research check.")

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
            prompt = f"""
            <date>
            {today_date}
            </date>

            <task>
            Provide today's comprehensive update on the following topic.
            Focus on the latest information, key developments, and the current situation.
            </task>
            
            <topic_query>
            {query}
            </topic_query>
            
            <output_format>
            Detailed text response, focusing on information relevant as of today.
            </output_format>
            """
            tasks_to_run[topic_key] = asyncio.create_task(
                get_completion(prompt=prompt, model_id=research_model_id),
                name=f"research_{topic_key}",  # Add name for easier debugging of async tasks
            )

    # 3. Run generation tasks concurrently if any are needed
    if tasks_to_run:
        logger.info(f"Generating research for {len(tasks_to_run)} topics...")
        try:
            results_list = await asyncio.gather(*tasks_to_run.values())
            new_results = dict(zip(tasks_to_run.keys(), results_list))

            # 4. Save new results to cache and update output dictionary
            save_tasks = []
            generation_errors = False
            for topic_key, result in new_results.items():
                if isinstance(result, Exception):  # Handle potential errors from individual generation tasks
                    logger.error(f"Research generation failed for topic {topic_key}: {result}")
                    generation_errors = True
                    break
                else:
                    logger.debug(f"Successfully generated research for topic: {topic_key}")
                    research_outputs[topic_key] = result
                    research_key = potential_keys_map[topic_key]
                    # Prepare save operations to run concurrently
                    save_tasks.append(handler.save_data(research_key, result, now))

            # Return error if any generation failed
            if generation_errors:
                logger.error("Aborting research process due to generation errors")
                return {"status": "error", "message": "Research generation failed for one or more topics", "values": {}}

            # Wait for all save operations to complete
            if save_tasks:
                logger.info(f"Saving {len(save_tasks)} new research results...")
                # Don't use return_exceptions to ensure all operations succeed
                try:
                    save_results = await asyncio.gather(*save_tasks)
                    # Verify all save operations succeeded
                    if not all(save_results):
                        logger.error("One or more save operations failed")
                        return {"status": "error", "message": "Failed to save one or more research topics", "values": {}}
                except Exception as e:
                    logger.error(f"Error saving research data: {e}")
                    return {"status": "error", "message": f"Error saving research data: {e}", "values": {}}

        except Exception as e:  # Catch errors during the gather/save process
            logger.error(f"Error during parallel research generation: {e}")
            return {"status": "error", "message": f"Error during research generation: {e}", "values": {}}

    # 5. Return final combined results only if we have results for all topics
    if len(research_outputs) != len(daily_research_topics):
        logger.error(f"Incomplete research results: {len(research_outputs)}/{len(daily_research_topics)} topics completed")
        return {
            "status": "error",
            "message": f"Incomplete research results: {len(research_outputs)}/{len(daily_research_topics)} topics completed",
            "values": {},
        }

    generated_count = len(tasks_to_run)
    cached_count = len(daily_research_topics) - generated_count
    message = f"Research complete. Generated: {generated_count}, Cached: {cached_count}."
    logger.info(message)

    return {"status": "success", "message": message, "values": {"daily_research_results": research_outputs}}


@tool
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

    # 1. Determine the actual topic to research
    actual_topic: Union[str, Dict[str, Any]]
    if topic is not None:
        actual_topic = topic
        logger.info("Using provided topic argument for research.")
    else:
        selected_topic = data_store.get("selected_topic")
        assert selected_topic, "Topic argument not provided and selected_topic not found in data_store"
        actual_topic = selected_topic
        logger.info("Using selected_topic from data_store for research.")

    assert isinstance(actual_topic, (str, dict)), "Resolved topic must be a string or a dictionary"

    # 2. Get required config
    config = data_store.get("config", {})
    research_model_id = config.get("ai_models", {}).get("research")
    assert research_model_id, "Researching model ID must be configured in ai_models"

    # 3. Construct the prompt
    today_date = datetime.utcnow().strftime("%Y-%m-%d")
    prompt = f"""
    <date>
    {today_date}
    </date>

    <task>
    Conduct detailed and comprehensive research on the following specific topic, provided below in the <topic_details> section.
    Expand on the provided details, find the latest developments, related news, background information,
    and provide in-depth analysis suitable for creating informative content (e.g., a detailed tweet thread or blog post section).
    Focus on accuracy, depth, and relevance as of today. Structure the output clearly.
    </task>

    <topic_details>
    {actual_topic}
    </topic_details>
    """

    # 4. Call the AI model
    try:
        research_result = await get_completion(prompt=prompt, model_id=research_model_id)

        logger.info(f"Successfully completed detailed research for the topic.")

        # 5. Return the result
        return {"status": "success", "message": f"Detailed research completed for the topic.", "values": {"context": research_result}}

    except Exception as e:
        logger.exception(f"Error during detailed research for the topic: {e}", exc_info=True)
        return {"status": "error", "message": f"Error during detailed research for the topic: {e}", "values": {}}
