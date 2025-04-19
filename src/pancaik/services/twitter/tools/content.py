"""
Twitter content tools for agents.

This module provides tools for generating and verifying Twitter content.
"""

import random
import re
from datetime import datetime, timedelta
from typing import Any, Dict

from ....core.config import logger
from ....tools.base import tool
from ....utils.ai_router import get_completion
from ....utils.json_parser import extract_json_content
from ..handlers import TwitterHandler


@tool
async def select_topics_from_followed_users(data_store: Dict[str, Any]):
    """
    Selects topics from tweets of followed users to generate content context.

    Fetches recent tweets from randomly selected followed users and
    analyzes them to create context for content inspiration.

    Args:
        data_store: Agent's data store containing configuration, state, and context

    Returns:
        Dictionary with operation status and values to be shared in data_store
    """
    # Preconditions
    assert data_store, "Data store must be provided"

    # Get required data
    config = data_store.get("config", {})
    twitter_config = config.get("twitter", {})
    followed_users = twitter_config.get("followed_users", {})

    # Validate we have followed users
    if not followed_users:
        logger.error("No followed users available")
        return {"status": "error", "message": "No followed users available"}

    # Select a random sample of users
    user_handles = list(followed_users.keys())
    selected_users = random.sample(user_handles, min(3, len(user_handles)))

    # Get recent tweets
    try:
        # Create handler for database operations
        handler = TwitterHandler()

        # Define the time window for recent tweets
        days_to_fetch = 3
        recent_date = datetime.utcnow() - timedelta(days=days_to_fetch)

        # Fetch recent tweets from the selected users with a single database call
        tweets = await handler.get_tweets_from_users(usernames=selected_users, min_date=recent_date, limit=30)

        if not tweets:
            logger.warning(f"No recent tweets found from selected users: {selected_users}")
            return {"status": "error", "message": "No recent tweets found from selected users"}

        # Prepare context
        posts = "\n\nPOSTS FROM FOLLOWED USERS:\n\n"
        for tweet in tweets:
            text = tweet.get("text", "")
            if text:
                posts += f"{tweet['username']}: {text}\n=======\n\n"

        # Create prompt for topic analysis
        prompt = f"""
        <profile>
        TODAY: {datetime.now().strftime("%Y-%m-%d")}
        ABOUT: {config.get("bio", "")}
        </profile>

        <task>
        Analyze the tweets from followed users and identify ONE high-quality topic for potential content creation.
        Determine if there is sufficient value to create a tweet based on the content analysis.
        Focus on topics that are timely, relevant to your profile, and would provide value to your audience.
        Extract complete information and preserve the full context of the content.
        </task>

        <instructions>
        1. Content Analysis:
           • Examine the tweets for recurring themes, unique insights, or emerging discussions
           • Look for topics with depth that allow for valuable commentary
           • Identify content that aligns with your profile's focus and expertise
           • Preserve complete facts and context from original tweets
        
        2. Topic Selection Criteria:
           • Relevance: Topic must be current and meaningful to your audience
           • Unique Angle: Preference for topics where you can offer a fresh perspective
           • Engagement Potential: Topics likely to generate meaningful interactions
           • Value Addition: Topics where your commentary adds genuine insight
        
        3. Decision Framework:
           • PROCEED when: You identify a topic that meets the above criteria with strong potential
           • DO NOT PROCEED when: The content is superficial, outdated, or misaligned with your profile
           
        4. Content Preservation:
           • Extract complete facts and details from the original tweets
           • Include full quotes when relevant
           • Preserve the nuance and specificity of the original content
        </instructions>

        <output_format>
        JSON format only. No extra text, just the json output.
        "should_proceed": true or false,
        "topic_chosen": "Detailed description of the selected topic",
        "rationale": "Complete explanation of why this topic was selected with specific reasoning",
        "full_context": "Complete context from the original tweets without summarization",
        "key_facts": "Complete factual information extracted from the content without omitting details",
        "original_tweets": "Direct quotes of the most relevant tweets, preserving their full content",
        "complete_analysis": "Comprehensive analysis of the topic including all relevant details and nuances",
        "relevance": "Detailed explanation of why this topic matters now with specific time-sensitive elements",
        "unique_angle": "Complete description of the perspective you can contribute",
        "talking_points": "Comprehensive list of points to address in your content, preserving specific details"
        </output_format>

        <content>
        {posts}
        </content>
        """

        # Get model ID from config
        model_id = config.get("ai_models", {}).get("analyzing")

        # Generate and process analysis
        try:
            response = await get_completion(prompt=prompt, model_id=model_id)
            analysis = extract_json_content(response)

            if not analysis or "should_proceed" not in analysis:
                logger.error("Failed to extract proper analysis from AI response")
                return {"status": "error", "message": "Failed to analyze content"}

            # Prepare context
            context = f"TOPIC ANALYSIS:\n{response}\n\n{posts}"

            # Return the status and values to be shared in data_store
            return {
                "status": "success",
                "message": f"Analyzed {len(tweets)} tweets from {len(selected_users)} users",
                "values": {"context": context, "topic_analysis": analysis, "analyzed_tweets": tweets, "selected_users": selected_users},
            }
        except Exception as e:
            logger.error(f"Error while analyzing topics: {str(e)}")
            return {"status": "error", "message": f"Error analyzing topics: {str(e)}"}

    except Exception as e:
        logger.error(f"Error while selecting topics from followed users: {str(e)}")
        return {"status": "error", "message": str(e)}


@tool
async def get_daily_content_from_followed_users(data_store: Dict[str, Any]):
    """
    Fetches the last day's tweets from all followed users.

    Retrieves tweets posted within the last 24 hours by every user
    listed in the configuration's followed_users section.

    Args:
        data_store: Agent's data store containing configuration, state, and context

    Returns:
        Dictionary with operation status and fetched content in the data_store values.
    """
    # Preconditions
    assert data_store, "Data store must be provided"

    # Get required data
    config = data_store.get("config", {})
    twitter_config = config.get("twitter", {})
    followed_users = twitter_config.get("followed_users", {})

    # Validate we have followed users
    if not followed_users:
        logger.error("No followed users available in config")
        return {"status": "error", "message": "No followed users available"}

    # Get all user handles
    user_handles = list(followed_users.keys())
    if not user_handles:
        logger.error("No user handles found in followed users")
        return {"status": "error", "message": "No user handles found"}

    # Get recent tweets
    try:
        # Create handler for database operations
        handler = TwitterHandler()

        # Define the time window for recent tweets (last 1 day)
        days_to_fetch = 1
        recent_date = datetime.utcnow() - timedelta(days=days_to_fetch)

        # Fetch recent tweets from all followed users
        tweets = await handler.get_tweets_from_users(usernames=user_handles, min_date=recent_date, limit=100000)

        if not tweets:
            logger.warning(f"No tweets found from followed users in the last {days_to_fetch} day(s)")
            # Return success even if no tweets, just empty content
            return {
                "status": "success",
                "message": f"No tweets found from {len(user_handles)} followed users in the last day.",
                "values": {"daily_content": ""},  # Return empty string if no tweets
            }

        # Format tweets into a single string
        daily_content_str = "\n\nDAILY CONTENT FROM FOLLOWED USERS:\n\n"
        for tweet in tweets:
            text = tweet.get("text", "")
            if text:
                daily_content_str += f"{tweet['username']}: {text}\n=======\n\n"

        # Return the status and formatted content string
        return {
            "status": "success",
            "message": f"Fetched and formatted {len(tweets)} tweets from {len(user_handles)} users from the last day.",
            "values": {"daily_content": daily_content_str},
        }

    except Exception as e:
        logger.error(f"Error while fetching daily content from followed users: {str(e)}")
        return {"status": "error", "message": f"Error fetching daily content: {str(e)}"}


@tool
async def compose_tweet_from_context(data_store: Dict[str, Any]):
    """
    Composes a tweet based on context in the data store using the configured AI model.

    Args:
        data_store: Agent's data store containing configuration, state, and context

    Returns:
        Dictionary with the generated tweet and operation status
    """
    # Preconditions
    assert data_store, "Data store must be provided"
    context = data_store.get("context")
    assert context, "Context must be available in the data store"

    config = data_store.get("config", {})
    twitter_config = config.get("twitter", {})

    # Determine character limit and get AI model
    is_premium = twitter_config.get("is_premium", False)
    chars_limit = twitter_config.get("single_tweet_chars_limit", 220) if is_premium else 220
    model_id = config.get("ai_models", {}).get("composing")
    username = twitter_config.get("credentials", {}).get("username", "")

    # Get style from config if available
    style_config = config.get("style", {})
    general_style = style_config.get("general", [])
    posts_style = style_config.get("posts", [])

    # Create prompt for tweet composition
    prompt = f"""
    <profile>
    USERNAME: {username}
    DATE: {datetime.now().strftime("%Y-%m-%d")}
    BIO: {config.get("bio", "")}
    </profile>
    
    <task>
    Compose a single engaging tweet based on the provided context.
    Create content that is insightful, concise, and aligned with the user's profile.
    </task>

    <constraints>
    • Maximum length: {chars_limit} characters
    • NO emojis
    • NO markdown formatting
    • NO hashtags
    • NO @mentions including your own username
    • NO direct replies to other users
    </constraints>

    <style_guidelines>
    GENERAL STYLE:
    {general_style}
    
    POSTS STYLE:
    {posts_style}
    </style_guidelines>
    
    <context>
    {context}
    </context>
    
    <output_format>
    JSON format with a single field.
    {{
      "tweet": "Your tweet here"
    }}
    No explanations or additional text - only the JSON output.
    </output_format>
    """

    try:
        # Generate and process tweet
        response = await get_completion(prompt=prompt, model_id=model_id)
        result = extract_json_content(response)

        if not result or "tweet" not in result:
            logger.error("Failed to extract tweet from AI response")
            return {"status": "error", "message": "Failed to generate tweet"}

        # remove hashtags
        tweet = re.sub(r"#\w+", "", result["tweet"]).strip()

        data_store["tweet"] = tweet
        return {"status": "success", "tweet": tweet}
    except Exception as e:
        logger.error(f"Error while composing tweet: {str(e)}")
        return {"status": "error", "message": str(e)}
