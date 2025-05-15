@tool
async def generate_daily_search_queries_from_research(data_store: Dict[str, Any]):
    """
    Generates daily search queries based on research findings.

    Takes the output from daily research and extracts key search terms for Twitter,
    identifying relevant keywords, hashtags, and accounts to search for engagement.

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
    guidelines = config.get("guidelines", "")

    # Get research results from data_store
    research_results = data_store.get("daily_research_results", {})
    assert research_results, "daily_research_results must be available in data_store"

    # Get optional daily content if available
    daily_content = data_store.get("daily_content", {})

    # Get query generation model
    query_model_id = config.get("ai_models", {}).get("analyzing")

    # Initialize database handler
    handler = DataHandler(collection_name="search_queries_cache")

    now = datetime.utcnow()
    today_date = now.strftime("%Y-%m-%d")

    # Check if we already have generated search queries for today
    cache_key = f"search_queries_{agent_id}_{today_date}"
    cached_queries = await handler.get_data_by_key(cache_key)

    if cached_queries:
        logger.info(f"Using cached search queries for agent {agent_id} dated {today_date}")
        return {
            "status": "success",
            "message": "Retrieved cached daily search queries",
            "values": {"daily_search_queries": cached_queries.get("content", {})},
        }

    # Create prompt with XML structure
    prompt = f"""
    <profile>
        TODAY: {today_date}
        ABOUT: {agent_bio}
    </profile>
    
    <task>
        Extract the most relevant search queries for Twitter based on the provided research data. 
        Focus on terms that will help find tweets the agent should engage with based on its mission and profile.
    </task>
    
    <guidelines>
    {guidelines}
    </guidelines>
    
    <context>
        Research data collected on {today_date}.
        {research_results}
        {f"Additional daily content: {daily_content}" if daily_content else ""}
    </context>
    
    <instructions>
        1. Analyze the research data to identify 80-100 key search queries based on relevant keywords, hashtags, and accounts.
        2. For each query, create a concise 'query_string' that will be used for Twitter search (e.g., hashtags, keywords, account names).
        3. Keep query strings very short, preferably 1-3 terms on average.
        4. Return the results in the specified structured JSON format.
    </instructions>
    
    <output_format>
    JSON output a list of, use standard json without any escaped or quoted text
        query_string: "The actual search query text",
        relevance_score: 0-100
    </output_format>
    """

    try:
        # Get completion and extract JSON content
        response = await get_completion(prompt=prompt, model_id=query_model_id)
        generated_queries = extract_json_content(response) or {}

        # If the dictionary has only one key, extract the first value
        if generated_queries and len(generated_queries.keys()) == 1:
            generated_queries = generated_queries[list(generated_queries.keys())[0]]

        # Save the generated queries to the database
        if await handler.save_data(cache_key, generated_queries, now):
            logger.info(f"Successfully generated and saved search queries for agent {agent_id}")
            return {
                "status": "success",
                "message": "Daily search queries generated and saved successfully",
                "values": {"daily_search_queries": generated_queries},
            }
        else:
            logger.error(f"Failed to save search queries for agent {agent_id}")
            return {
                "status": "error",
                "message": "Failed to save generated search queries",
                "values": {"daily_search_queries": generated_queries},
            }
    except Exception as e:
        logger.error(f"Error during search query generation: {e}")
        return {"status": "error", "message": f"Search query generation failed: {str(e)}", "values": {}}