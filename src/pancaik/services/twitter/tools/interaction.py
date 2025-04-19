"""
Twitter interaction tools for agents.

This module provides tools for interacting with tweets and mentions.
"""

import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from ....core.config import logger
from ....tools.base import tool
from ....utils.ai_router import get_completion
from ....utils.json_parser import extract_json_content
from .. import client
from ..handlers import TwitterHandler


async def get_conversation(post: Dict, credentials: Dict, handler: TwitterHandler, depth: int = 10) -> Tuple[str, int, int]:
    """
    Retrieves the conversation thread for a given post.

    Args:
        post: The tweet/post to retrieve conversation for
        credentials: Twitter API credentials
        handler: TwitterHandler instance for database operations
        depth: Maximum depth of conversation thread to retrieve

    Returns:
        Tuple of (conversation_text, reply_count, handle_count)
    """
    # Preconditions
    assert post, "Post must be provided"
    assert credentials, "Credentials must be provided"
    assert handler, "TwitterHandler must be provided"
    assert isinstance(handler, TwitterHandler), "handler must be a TwitterHandler instance"

    agent_user = credentials.get("username")
    assert agent_user, "Username must be in credentials"

    def remove_mentions(text):
        return re.sub(r"@\w+", "", text).strip()

    def count_handles(text):
        return len(re.findall(r"@\w+", text))

    visited_level = 0
    posts = {}
    posts[post["_id"]] = post
    current_post = post

    # Get collection for database operations
    collection = handler.get_collection()

    # Get all parent posts in the conversation
    while visited_level < depth and current_post.get("replied_to_id"):
        post_id = str(current_post.get("replied_to_id"))
        # top of conversation
        if not post_id:
            break

        # Use the handler's collection to find the parent post
        parent_post = await collection.find_one({"_id": str(post_id)})

        if not parent_post:
            # Fetch from Twitter API if not in database
            parent_post = await client.get_tweet(post_id, credentials)
            if parent_post:
                # Use the handler to insert the new tweet
                await handler.insert_tweets([parent_post])

        if not parent_post:
            # Fail task as we can't reconstruct the conversation
            raise Exception(f"Failed to retrieve tweet {post_id}. Cannot reconstruct conversation.")

        posts[parent_post["_id"]] = parent_post
        current_post = parent_post
        visited_level += 1

    # Reconstruct conversation in chronological order
    conversation_array = []
    current_post = post

    # Find the oldest parent post
    while current_post.get("replied_to_id"):
        post_id = str(current_post.get("replied_to_id"))
        if post_id not in posts:
            break
        current_post = posts[post_id]

        text = remove_mentions(current_post.get("text", ""))
        username = current_post.get("username") or current_post.get("user_id") or "Other User"
        conversation_array.insert(0, f"{username}: {text}")

    # Join the conversation messages
    history = "\n".join(conversation_array)

    # Count replies from agent user
    count_replies = sum(1 for msg in conversation_array[1:] if agent_user in msg)

    # Add the current post text
    text = remove_mentions(post.get("text", ""))
    username = post.get("username") or post.get("user_id") or "Other User"

    # Format the complete conversation context
    conversation = f"""
    <post_type>
    You are about to reply to a post. 
    Make sure you understand the context of the conversation before proceeding.
    Make sure you reply to the post by user.
    Reply must be 180 chars or less
    </post_type>

    <conversation>
    {history}
    </conversation>

    <reply_to>
    {f"{username}: {text}"}
    </reply_to>
    """

    # Return the conversation text, reply count, and handle count
    return conversation, count_replies, count_handles(post["text"])


@tool
async def select_mention_to_reply(data_store: Dict[str, Any]):
    """
    Selects an unresponded mention to reply to from the Twitter database.

    Args:
        data_store: Agent's data store containing configuration and state

    Returns:
        Dictionary with selected mention context or False if no suitable mentions found
    """
    # Preconditions
    assert data_store, "Data store must be provided"

    # Extract required configuration from data_store
    credentials = data_store.get("config", {}).get("twitter", {}).get("credentials", {})
    assert credentials, "Twitter credentials must be in the agent's data store"

    # Get the username for constructing the query
    username = credentials.get("username")
    assert username, "Twitter username must be in the credentials"

    # Get the configuration limits
    twitter_config = data_store.get("config", {}).get("twitter", {})
    max_thread_replies = twitter_config.get("max_thread_replies", 3)
    max_mentioned_users = twitter_config.get("max_mentioned_users_to_include_in_reply", 2)

    # Ensure we have a handler for database operations
    handler = TwitterHandler()
    collection = handler.get_collection()

    # Select all mentions not yet replied to
    query = {
        "$and": [
            {"mentions.username": username},
            {"replied_by": {"$nin": [username]}},
            {"username": {"$ne": username}},
        ]
    }

    # Search for mentions
    mentions = await collection.find(query).sort([("created_at", -1)]).to_list(length=1000)

    # Remove RT by self
    mentions = [mention for mention in mentions if not mention.get("text", "").startswith("RT @" + username)]

    # Create the default return for no mentions case
    status = "no_mentions_found" if not mentions else "no_suitable_mentions"

    # Iterate through mentions until we find a suitable one
    for mention in mentions:
        try:
            # Get full conversation
            conversation, count_replies, handle_count = await get_conversation(mention, credentials, handler)
        except Exception as e:
            logger.warning(f"Error in get_conversation for mention {mention.get('_id')}: {e}", exc_info=True)
            return {
                "status": "error",
                "should_exit": True,
                "error": str(e),
                "mention_id": mention.get("_id"),
            }

        # Determine if we should reply
        should_reply = handle_count <= max_mentioned_users and count_replies < max_thread_replies

        if should_reply:
            logger.info(f"Selected mention {mention['_id']} to reply to")
            return {
                "status": "success",
                "mention_id": mention["_id"],
                "conversation": conversation,
                "values": {"context": conversation, "reply_to_id": mention["_id"]},
            }
        else:
            # Mark as reviewed only if not suitable
            await collection.update_one({"_id": mention["_id"]}, {"$push": {"replied_by": username}})
            logger.info(
                f"Mention {mention['_id']} not suitable for reply (handle_count={handle_count}, count_replies={count_replies}). Marked as reviewed and continuing to next mention."
            )

    # If we've gone through all mentions and none are suitable
    logger.info(f"No {'unreplied' if not mentions else 'suitable'} mentions found")
    return {"status": status, "username": username, "values": {}}


async def determine_eligible_users(user_handles: list, username: str, followed_users: dict, time_limits: dict, collection):
    """
    Determines which users are eligible for interaction based on time limits between interactions.

    Args:
        user_handles: List of user handles to check
        username: The username of the agent
        followed_users: Dictionary containing user-specific configurations
        time_limits: Dictionary containing default time limits for different interaction types
        collection: MongoDB collection to query

    Returns:
        Dictionary of eligible users and their eligible interaction types
    """
    # Use MongoDB aggregation to get the most recent interactions for all users at once
    now = datetime.utcnow()

    pipeline = [
        # Match documents where our agent has interacted with the followed users
        {"$match": {"username": {"$in": user_handles}, "interactions_by": username}},
        # Group by username and interaction_type to get the most recent interaction of each type
        {"$group": {"_id": {"username": "$username", "interaction_type": "$interaction_type"}, "created_at": {"$max": "$created_at"}}},
    ]

    # Execute the aggregation
    user_interactions_cursor = collection.aggregate(pipeline)
    user_interactions_list = await user_interactions_cursor.to_list(length=None)

    # Process eligibility for each user
    eligible_users = {}

    for user in user_handles:
        # Check if this user has custom time limit settings
        user_config = followed_users.get(user, {})
        user_time_limits = {
            "replies": user_config.get("replies_min_hours_between", time_limits["replies"]),
            "quotes": user_config.get("quotes_min_hours_between", time_limits["quotes"]),
            "retweets": user_config.get("retweets_min_hours_between", time_limits["retweets"]),
        }

        # Determine eligibility for each interaction type
        eligibility = {"replies": True, "quotes": True, "retweets": True}

        # Check each interaction type against time limits
        for interaction_type, limit_hours in user_time_limits.items():
            # Find the relevant interaction record from our aggregation results
            for interaction in user_interactions_list:
                if interaction["_id"]["username"] == user and interaction["_id"]["interaction_type"] == interaction_type:
                    # Calculate hours since last interaction
                    last_time = interaction["created_at"]
                    hours_since = (now - last_time).total_seconds() / 3600
                    if hours_since < limit_hours:
                        eligibility[interaction_type] = False
                    break

        # Add to eligible users if any interaction type is eligible
        if any(eligibility.values()):
            eligible_users[user] = eligibility

    return eligible_users


@tool
async def select_post_from_followed_user_to_comment(data_store: Dict[str, Any]):
    """
    Selects a post from a followed user to comment on, quote, or retweet.
    Analyzes up to 15 recent tweets from the last 7 days using an AI model.
    Respects time limits between interactions.

    Args:
        data_store: Agent's data store containing configuration and state

    Returns:
        Dictionary with selected post context or status if no suitable posts found
    """
    # Preconditions
    assert data_store, "Data store must be provided"

    # Extract required configuration from data_store
    config = data_store.get("config", {})
    twitter_config = config.get("twitter", {})
    assert twitter_config, "Twitter configuration must be in the agent's data store"

    credentials = twitter_config.get("credentials", {})
    assert credentials, "Twitter credentials must be in the agent's data store"

    username = credentials.get("username")
    assert username, "Twitter username must be in the credentials"

    followed_users = twitter_config.get("followed_users", {})
    assert isinstance(followed_users, dict), "followed_users should be a dictionary where keys are Twitter handles"

    if not followed_users:
        logger.warning("No Twitter followed users found in config to select posts from.")
        return {"status": "no_followed_users", "values": {}}

    user_handles = list(followed_users.keys())

    # Initialize handler for database operations
    handler = TwitterHandler()
    collection = handler.get_collection()

    # Fetch time limit configuration
    time_limits = {
        "replies": twitter_config.get("default_replies_min_hours_between", 72),
        "quotes": twitter_config.get("default_quotes_min_hours_between", 72),
        "retweets": twitter_config.get("default_retweets_min_hours_between", 72),
    }

    # Determine which users are eligible for interaction
    eligible_users = await determine_eligible_users(
        user_handles=user_handles, username=username, followed_users=followed_users, time_limits=time_limits, collection=collection
    )

    # If no eligible users, return early
    if not eligible_users:
        logger.info("No eligible users found based on interaction time limits")
        return {"status": "no_eligible_users", "values": {}, "should_exit": True}

    # Define time window (last 7 days)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)

    # Construct query to find recent posts from eligible users not interacted with
    query = {
        "username": {"$in": list(eligible_users.keys())},
        "created_at": {"$gte": seven_days_ago},
        # Ensure it's not a reply to the agent itself (avoid self-loops)
        "replied_to_username": {"$ne": username},
        # Exclude posts already interacted with by this agent
        "$or": [
            {"interactions_by": {"$exists": False}},
            {"interactions_by": {"$nin": [username]}},
        ],
        # Exclude retweets
        "retweeted_status": {"$exists": False},
    }

    # Search for posts
    posts = await collection.find(query).sort([("created_at", -1)]).to_list(length=100)

    if not posts:
        logger.info(f"No recent, un-interacted posts found from followed users: {', '.join(user_handles)}")
        return {"status": "no_suitable_posts", "values": {}}

    # Process up to most recent posts
    posts_to_consider = posts[:5]

    logger.info(f"Found {len(posts_to_consider)} posts from followed users to consider for commenting.")

    for post in posts_to_consider:
        post_id = post["_id"]
        post_username = post["username"]
        post_text = post.get("text", "")
        logger.info(f"Considering post {post_id} from user {post_username}")

        # Get user's eligibility status
        user_eligibility = eligible_users.get(post_username, {})

        try:
            # Check if we already have an analysis for this post by this username
            existing_analysis = post.get("analyses", {}).get(username)
            if existing_analysis:
                analysis_timestamp = post.get("analyses", {}).get(f"{username}_timestamp")
                logger.info(f"Found existing analysis for post {post_id} from {username} created at {analysis_timestamp}")
                analysis_result = existing_analysis
            else:
                # 1. Analyze post with AI
                prompt = f"""
                <profile>
                TODAY: {datetime.utcnow().strftime("%Y-%m-%d")}
                ABOUT: {config.get("bio", "")}
                </profile>
                
                <task>
                Analyze the following Twitter post and decide your action: reply, quote, retweet, or ignore.
                Ensure that any interaction adds value to the conversation. If the post doesn't meet the criteria for adding value, ignore it.
                Always prioritize replies, then retweets, and finally quotes.
                </task>
                
                <instructions>
                    1. Contextual Understanding:
                    • Conduct extensive online research using multiple verified sources (news outlets, academic sources, official websites, etc.) to gather a comprehensive context for the post.
                    • Analyze the content and identify any recent developments related to the topic from credible online resources.
                
                    2. Decision Making:
                    • Reply: Engage directly with the post if it aligns with the character's voice and can benefit from a witty, insightful comment.
                    • Quote: Share the post on your timeline with added commentary if it contributes meaningfully to the broader conversation.
                
                    3. Value Addition:
                    • Ensure that any reply or quote provides clarity, humor, or insightful critique, and is respectful and constructive.
                
                    4. Relevance:
                    • Interact only if the post is relevant to current trends, discussions, or offers a unique perspective worth addressing.
                </instructions>
                
                <research>
                Before deciding to reply or quote, conduct thorough research using reliable online resources to validate and understand the post's content. Your analysis should include:
                    • Post Validity:
                        - Accuracy of Claims: Verify the factual correctness of any statements or claims made in the post through reputable online sources.
                        - Source Reliability: Assess the credibility of the original poster and any referenced sources or entities using online verification.
                    • Contextual Background:
                        - Gather background information from trusted websites, news articles, and academic publications to understand the broader context surrounding the post.
                    • Community Sentiment:
                        - Public Opinion: Look beyond Twitter to gauge community reactions and opinions from multiple online platforms.
                        - Divergent Views: Identify differing perspectives or debates that the post may be contributing to or sparking, using verified online discussions.
                    • Veracity and Misconceptions:
                        - Fact-Checking: Cross-reference the post's information with multiple reputable sources (e.g., fact-checking websites, official reports) to confirm its veracity.
                        - Potential Misinterpretations: Analyze how the post could be misconstrued or misrepresented, and prepare to address possible misunderstandings.
                    • Connected Discussions:
                        - Trending Topics: Identify if the post is part of a larger trending topic or movement online.
                    • Impact Analysis:
                        - Influence: Determine the potential influence of the post on public discourse and the topic at hand.
                        - Engagement Potential: Evaluate whether interacting with the post will foster meaningful dialogue or enhance understanding.
                </research>
                
                <output_format>
                OUTPUT IN JSON: Strict JSON format, no additional text.
                "should_retweet": true or false,
                "should_reply": true or false,
                "should_quote": true or false,
                "how_it_fits_the_character_narrative": "Explanation of how the post aligns with the narrative",
                "accuracy_of_claims": "Detailed analysis of the factual correctness of the post.",
                "source_reliability": "Evaluation of the credibility of {post_username} and any referenced entities.",
                "contextual_background": "Background information gathered from verified online resources related to the post",
                "public_opinion": "Summary of community reactions and sentiments gathered from multiple platforms.",
                "divergent_views": "Overview of differing opinions or debates sparked by the post.",
                "fact_checking": "Results of cross-referencing the post's information with reputable online sources.",
                "potential_misinterpretations": "Analysis of how the post could be misconstrued.",
                "trending_topics": "Identification of any larger trends or movements the post is part of.",
                "influence": "Assessment of the post's potential influence on public discourse.",
                "engagement_potential": "Evaluation of whether interacting will foster meaningful dialogue.",
                "research_summary": "Summary of the research gathered from verified online sources to complement the reply."
                </output_format>
                
                <post>
                BY TWITTER USER: {post_username}
                CONTENT: {post_text}
                </post>
                """

                # Get model ID from config
                model_id = config.get("ai_models", {}).get("research-mini")

                # Call AI model using get_completion from utils.ai_router
                ai_response_text = await get_completion(prompt=prompt, model_id=model_id)

                if not ai_response_text:
                    logger.warning(f"AI analysis failed for post {post_id}")
                    continue

                # Extract JSON analysis
                analysis_result = extract_json_content(ai_response_text)
                if not analysis_result or not isinstance(analysis_result, dict):
                    logger.warning(
                        f"Failed to extract valid JSON analysis from AI response for post {post_id}. Response: {ai_response_text}"
                    )
                    continue

                logger.info(f"AI Analysis for {post_id}")

            # 3. Check interaction logic

            # --- Check Retweet ---
            if analysis_result.get("should_retweet") and user_eligibility.get("retweets", False):

                # directly retweet
                resp = await client.create_tweet(credentials, "", quote_id=post_id)

                # Mark as interacted directly for retweet
                await collection.update_one(
                    {"_id": post_id},
                    {"$push": {"interactions_by": username}, "$set": {"interaction_type": "retweets", "retweeted_at": datetime.utcnow()}},
                )

                logger.info(f"Post {post_id} from @{post_username} was retweeted by {username}")

                # Return with should_exit flag to stop further pipeline processing
                return {
                    "status": "success",
                    "should_exit": True,
                }

            # --- Check Reply ---
            if analysis_result.get("should_reply") and user_eligibility.get("replies", False) and post.get("replied_to_id") is None:

                # Prepare reply context without getting conversation (since we only want original posts)
                context = f"""
                <post_type>
                You are replying to a post.
                Make sure you reply to the post by user.
                Reply must be 180 chars or less
                </post_type>

                <original_post>
                @{post_username}: {post_text}
                </original_post>
                
                <action>reply</action>
                """

                logger.info(f"Selected post {post_id} from @{post_username} for replying")
                return {
                    "status": "success",
                    "post_id": post_id,
                    "post_username": post_username,
                    "interaction_type": "reply",
                    "values": {"context": context, "reply_to_id": post_id, "interaction_type": "reply"},
                }

            # --- Check Quote ---
            if analysis_result.get("should_quote") and user_eligibility.get("quotes", False):

                # Prepare context for quote tweet
                context = f"""
                <post_type>
                You are quoting a post with your own commentary.
                Your comment must be insightful and add value.
                Keep your comment 180 chars or less.
                </post_type>
                
                <original_post>
                @{post_username}: {post_text}
                </original_post>
                
                <analysis>{analysis_result}</analysis>
                """

                logger.info(f"Selected post {post_id} from @{post_username} for quoting")
                return {
                    "status": "success",
                    "post_id": post_id,
                    "post_username": post_username,
                    "interaction_type": "quote",
                    "values": {"context": context, "quote_tweet_id": post_id, "interaction_type": "quote"},
                }

            # If AI suggested an interaction but time limits prevent it, save the analysis for future use
            if analysis_result.get("should_retweet") or analysis_result.get("should_reply") or analysis_result.get("should_quote"):
                logger.info(
                    f"Post {post_id} has a recommended action, but time limits prevent interaction. Saving analysis for future reference."
                )
                await collection.update_one(
                    {"_id": post_id},
                    {"$set": {f"analyses.{username}": analysis_result, f"analyses.{username}_timestamp": datetime.utcnow()}},
                )
                continue

            # If AI explicitly suggested to ignore the post
            if not any([analysis_result.get("should_retweet"), analysis_result.get("should_reply"), analysis_result.get("should_quote")]):
                # Mark the post as ignored so we don't analyze it again
                await collection.update_one(
                    {"_id": post_id},
                    {
                        "$push": {"interactions_by": username},
                        "$set": {
                            "interaction_type": "ignored",
                            "ignored_at": datetime.utcnow(),
                            f"analyses.{username}": analysis_result,
                            f"analyses.{username}_timestamp": datetime.utcnow(),
                        },
                    },
                )
                logger.info(f"Marked post {post_id} as ignored as AI recommended no action")

        except Exception as e:
            logger.error(f"Error processing post {post_id} in select_post_from_followed_user_to_comment: {e}", exc_info=True)
            continue  # Move to the next post

    logger.info("None of the considered posts resulted in an interaction (reply/retweet/quote).")
    return {"status": "no_suitable_posts_after_analysis", "values": {}, "should_exit": True}


@tool
async def mark_mention_as_reviewed(data_store: Dict[str, Any], reply_to_id: str):
    """
    Marks a tweet/mention as reviewed without responding to it.

    Args:
        data_store: Agent's data store containing configuration and state
        reply_to_id: ID of the tweet to mark as reviewed

    Returns:
        Dictionary with status of the operation
    """
    # Preconditions
    assert data_store, "Data store must be provided"

    # Extract required configuration from data_store
    credentials = data_store.get("config", {}).get("twitter", {}).get("credentials", {})
    assert credentials, "Twitter credentials must be in the agent's data store"

    # Get the username for recording who reviewed
    username = credentials.get("username")
    assert username, "Twitter username must be in the credentials"

    assert reply_to_id, "Tweet ID must be provided"

    # Initialize handler for database operations
    handler = TwitterHandler()
    collection = handler.get_collection()

    # Mark the tweet as reviewed
    result = await collection.update_one({"_id": reply_to_id}, {"$push": {"replied_by": username}})

    if result.modified_count > 0:
        logger.info(f"Tweet {reply_to_id} marked as reviewed by {username}")
        status = "success"
    else:
        logger.warning(f"Failed to mark tweet {reply_to_id} as reviewed (tweet may not exist)")
        status = "error"

    return {"status": status}


@tool
async def mark_post_as_commented(
    data_store: Dict[str, Any], reply_to_id: Optional[str] = None, quote_tweet_id: Optional[str] = None, interaction_type: str = None
):
    """
    Marks a post as interacted with after successful interaction (reply, quote, retweet).

    Args:
        data_store: Agent's data store containing configuration and state
        reply_to_id: ID of the post that was replied to (for replies and retweets)
        quote_tweet_id: ID of the post that was quoted (for quotes)
        interaction_type: Type of interaction ('reply', 'quote', 'retweet')

    Returns:
        Dictionary with status of the operation
    """
    # Preconditions
    assert data_store, "Data store must be provided"
    assert reply_to_id or quote_tweet_id, "Either reply_to_id or quote_tweet_id must be provided"
    assert interaction_type in ["reply", "quote", "retweet"], "Interaction type must be one of: reply, quote, retweet"

    # Determine which ID to use based on interaction type
    post_id = reply_to_id if interaction_type in ["reply", "retweet"] else quote_tweet_id
    assert post_id, "Post ID must be provided"

    # Extract required configuration from data_store
    credentials = data_store.get("config", {}).get("twitter", {}).get("credentials", {})
    assert credentials, "Twitter credentials must be in the agent's data store"

    # Get the username for recording who interacted
    username = credentials.get("username")
    assert username, "Twitter username must be in the credentials"

    # Initialize handler for database operations
    handler = TwitterHandler()
    collection = handler.get_collection()

    # Map interaction types to database field names for tracking
    interaction_type_map = {"reply": "replies", "quote": "quotes", "retweet": "retweets", "ignored": "ignored"}

    db_interaction_type = interaction_type_map.get(interaction_type, interaction_type)

    # Mark the post as interacted with
    # 1. Add username to interactions_by array
    # 2. Add current timestamp
    # 3. Set the interaction_type field for tracking time limits
    update_data = {
        "$push": {"interactions_by": username},
        "$set": {"interaction_type": db_interaction_type, "created_at": datetime.utcnow()},
    }

    result = await collection.update_one({"_id": post_id}, update_data)

    if result.modified_count > 0:
        logger.info(f"Post {post_id} marked as {interaction_type}d by {username}")
        status = "success"
    else:
        logger.warning(f"Failed to mark post {post_id} as {interaction_type}d (post may not exist)")
        status = "error"

    return {"status": status}
