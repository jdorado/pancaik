"""
Topic generation tools for agents.

This module provides tools for generating and managing topics based on research.
"""

from datetime import datetime
from typing import Any, Dict

from ..core.config import logger
from ..core.data_handler import DataHandler
from ..tools.base import tool
from ..utils.ai_router import get_completion
from ..utils.json_parser import extract_json_content


@tool
async def generate_daily_topics_from_research(data_store: Dict[str, Any]):
    """
    Generates daily topics based on research findings.

    Takes the output from daily research and extracts key topics for content creation,
    identifying trending subjects, emerging patterns, and high-value discussion areas.

    Args:
        data_store: Agent's data store containing configuration, state, and context

    Returns:
        Dictionary with operation status and values to be shared in data_store
    """
    assert data_store, "Data store must be provided"

    # Get necessary configuration
    config = data_store.get("config", {})

    # Get agent_id, required for per-agent storage
    agent_id = data_store.get("agent_id")
    assert agent_id, "agent_id must be configured"

    # Get agent profile/bio
    agent_bio = config.get("bio", "")

    # Get research results from data_store
    research_results = data_store.get("daily_research_results", {})
    assert research_results, "daily_research_results must be available in data_store"

    # Get optional daily content if available
    daily_content = data_store.get("daily_content", {})

    # Get topic generation model
    topic_model_id = config.get("ai_models", {}).get("analyzing")

    # Initialize database handler
    handler = DataHandler(collection_name="topics_cache")

    now = datetime.utcnow()
    today_date = now.strftime("%Y-%m-%d")

    # Check if we already have generated topics for today
    cache_key = f"topics_{agent_id}_{today_date}"
    cached_topics = await handler.get_data_by_key(cache_key)

    if cached_topics:
        logger.info(f"Using cached topics for agent {agent_id} dated {today_date}")
        return {
            "status": "success",
            "message": "Retrieved cached daily topics",
            "values": {"daily_topics": cached_topics.get("content", {})},
        }

    # Create prompt with XML structure
    prompt = f"""
    <profile>
        TODAY: {today_date}
        ABOUT: {agent_bio}
    </profile>
    
    <task>
        Extract the most significant and specific recent updates, announcements, or factual developments from the provided research data. Focus on tweetable, newsworthy information that aligns with the agent's mission and profile. Prioritize concrete details over general summaries.
    </task>
    
    <context>
        Research data collected on {today_date}.
        {research_results}
        {f"Additional daily content: {daily_content}" if daily_content else ""}
    </context>
    
    <instructions>
        1. Analyze the research data to identify 5-20 key topics based on the most recent and specific updates, announcements, or factual data points (e.g., new project features, specific company actions, key statistics like diagnostic accuracy improvements).
        2. For each topic, create a concise 'excerpt' that highlights the core news or fact, suitable for a tweet. Include specific names, numbers, and event details. Avoid generic statements.
        3. Ensure topics are distinct and focus on concrete information rather than broad trends unless a specific new data point about the trend is mentioned.
        4. Categorize each topic appropriately based on its content.
        5. Assign relevance scores based on the agent's mission and the specificity/impact of the information.
        6. Return the results in the specified structured JSON format.
    </instructions>
    
    <output_format>
    JSON output a list of, use standard json without any escaped or quoted text
        title: "topic title",
        excerpt: "Key excerpt including relevant facts, names, and events",
        theme: "relevant theme",
        category: "One of: explanation, update, framework, use case, trend, opinion",
        full_context: "Complete topic content or extended context",
        relevance_score: 0-100
    </output_format>
    """

    try:
        # Get completion and extract JSON content
        response = await get_completion(prompt=prompt, model_id=topic_model_id)
        generated_topics = extract_json_content(response) or {}

        # If the dictionary has only one key, extract the first value
        if generated_topics and len(generated_topics.keys()) == 1:
            generated_topics = generated_topics[list(generated_topics.keys())[0]]

        # Save the generated topics to the database
        if await handler.save_data(cache_key, generated_topics, now):
            logger.info(f"Successfully generated and saved topics for agent {agent_id}")
            return {
                "status": "success",
                "message": "Daily topics generated and saved successfully",
                "values": {"daily_topics": generated_topics},
            }
        else:
            logger.error(f"Failed to save topics for agent {agent_id}")
            return {"status": "error", "message": "Failed to save generated topics", "values": {"daily_topics": generated_topics}}
    except Exception as e:
        logger.error(f"Error during topic extraction: {e}")
        return {"status": "error", "message": f"Topic extraction failed: {str(e)}", "values": {}}


@tool
async def select_topics_from_daily_research(data_store: Dict[str, Any]):
    """
    Selects the most relevant, unposted topic from the daily generated topics.

    Retrieves daily topics, filters out those already marked as posted, ranks
    the remaining by relevance score, and selects the top one.

    Args:
        data_store: Agent's data store containing daily_topics.

    Returns:
        Dictionary with operation status and the selected topic added to values.
    """
    assert data_store, "Data store must be provided"

    daily_topics = data_store.get("daily_topics")
    assert daily_topics is not None, "daily_topics must be available in data_store"
    assert isinstance(daily_topics, list), "daily_topics must be a list"

    agent_id = data_store.get("agent_id")
    assert agent_id, "agent_id must be configured"

    logger.debug(f"Selecting topic for agent {agent_id} from {len(daily_topics)} topics.")

    # Filter out topics marked as posted
    unposted_topics = [topic for topic in daily_topics if isinstance(topic, dict) and not topic.get("is_posted", False)]

    if not unposted_topics:
        logger.info(f"No unposted topics available for agent {agent_id}.")
        return {"status": "success", "message": "No unposted topics available", "values": {"selected_topic": None}}

    # Sort by relevance_score descending
    try:
        sorted_topics = sorted(unposted_topics, key=lambda x: x.get("relevance_score", 0), reverse=True)
    except TypeError as e:
        logger.error(f"Error sorting topics for agent {agent_id}: {e}. Topics: {unposted_topics}")
        return {"status": "error", "message": f"Error sorting topics: {e}", "values": {}}

    selected_topic = sorted_topics[0]
    logger.info(f"Selected topic for agent {agent_id}: '{selected_topic.get('title')}'")

    return {"status": "success", "message": "Top relevant unposted topic selected", "values": {"selected_topic": selected_topic}}


@tool
async def mark_topic_as_posted(data_store: Dict[str, Any]):
    """
    Marks the selected topic as posted in the daily topics cache.

    Retrieves the selected topic, finds it in the cached daily topics list
    for the current agent and date, adds an 'is_posted: True' flag,
    and saves the updated list back to the cache.

    Args:
        data_store: Agent's data store containing selected_topic and agent_id.

    Returns:
        Dictionary with operation status.
    """
    assert data_store, "Data store must be provided"

    selected_topic = data_store.get("selected_topic")
    assert selected_topic, "selected_topic must be available in data_store"
    assert isinstance(selected_topic, dict), "selected_topic must be a dictionary"

    agent_id = data_store.get("agent_id")
    assert agent_id, "agent_id must be configured"

    # Use title and excerpt as a composite key for finding the topic, assuming they are unique enough
    topic_key = (selected_topic.get("title"), selected_topic.get("excerpt"))
    assert topic_key[0] is not None, "Selected topic must have a title"
    assert topic_key[1] is not None, "Selected topic must have an excerpt"

    handler = DataHandler(collection_name="topics_cache")
    now = datetime.utcnow()
    today_date = now.strftime("%Y-%m-%d")
    cache_key = f"topics_{agent_id}_{today_date}"

    # Fetch current cached topics
    cached_data = await handler.get_data_by_key(cache_key)
    if not cached_data or "content" not in cached_data or not isinstance(cached_data["content"], list):
        logger.error(f"Could not find or parse cached topics for key {cache_key}")
        return {"status": "error", "message": f"Failed to retrieve valid cached topics for {today_date}"}

    cached_topics = cached_data["content"]
    updated = False
    for i, topic in enumerate(cached_topics):
        if isinstance(topic, dict) and (topic.get("title"), topic.get("excerpt")) == topic_key:
            cached_topics[i]["is_posted"] = True
            updated = True
            logger.info(f"Marking topic '{topic_key[0]}' as posted for agent {agent_id}")
            break

    if not updated:
        logger.warning(f"Could not find topic '{topic_key[0]}' in cache {cache_key} to mark as posted.")
        # Decide if this is an error or just a warning. For now, proceed but log.
        return {"status": "warning", "message": "Selected topic not found in cache to mark as posted."}

    # Save the updated list back to the cache
    if await handler.save_data(cache_key, cached_topics, now):
        logger.info(f"Successfully updated topics cache {cache_key} with posted status.")
        return {"status": "success", "message": "Topic marked as posted successfully in cache"}
    else:
        logger.error(f"Failed to save updated topics cache {cache_key}")
        return {"status": "error", "message": "Failed to save updated topics cache"}
