"""
Website Crawler tool for Pancaik agents.

This tool intelligently crawls websites to extract specific content based on natural language requirements.
It automatically detects URLs from context and handles all crawling parameters intelligently.

# - Tool is always async, no nested functions, keep it simple
# - Return {values: {context: {new_key: new_value}}} and use descriptive, globally-unique keys
# - Add 'should_exit': True to the return dict to gracefully end the pipeline when needed
# - Use a proper name to identify the output in a global context (avoid ambiguous names)
# - Do NOT use try/catch in the tool (the @tool decorator handles exceptions)
# - Follow the sample code pattern and keep code modular, clear, and open source quality
"""

import asyncio
import hashlib
from datetime import datetime
from typing import Any, Dict
from pydantic import BaseModel, create_model

from ..core.config import logger, get_config
from ..core.data_handler import DataHandler
from ..utils.ai_router import get_completion
from ..utils.json_parser import extract_json_content
from ..utils.prompt_utils import get_prompt
from .base import tool


async def firecrawl_extract_async(api_key: str, urls: list, prompt: str, schema_dict: dict) -> dict:
    """
    Async wrapper for Firecrawl extraction.
    
    Args:
        api_key: Firecrawl API key
        urls: List of URLs to crawl
        prompt: Extraction prompt
        schema_dict: Pydantic schema dictionary
        
    Returns:
        Extracted data from Firecrawl
    """
    def _sync_extract():
        try:
            from firecrawl import FirecrawlApp
            
            # Initialize FirecrawlApp
            app = FirecrawlApp(api_key=api_key)
            
            # Create dynamic Pydantic model from schema_dict
            fields = {}
            for field_name, field_info in schema_dict.items():
                field_type = field_info.get("type", "str")
                field_description = field_info.get("description", "")
                
                # Map string types to Python types
                type_mapping = {
                    "str": str,
                    "bool": bool,
                    "int": int,
                    "float": float,
                    "list": list,
                }
                
                python_type = type_mapping.get(field_type, str)
                fields[field_name] = (python_type, ...)
            
            # Create dynamic model
            ExtractSchema = create_model('ExtractSchema', **fields)
            
            # Perform extraction
            response = app.extract(urls, prompt=prompt, schema=ExtractSchema.model_json_schema())
            
            # Extract only the data field from the ExtractResponse object
            if hasattr(response, 'data') and response.data:
                return response.data
            elif hasattr(response, '__dict__'):
                # Fallback: convert to dict and extract data
                response_dict = response.__dict__ if hasattr(response, '__dict__') else {}
                return response_dict.get('data', {})
            else:
                return response
            
        except Exception as e:
            logger.error(f"Firecrawl extraction failed: {str(e)}")
            return {"error": str(e)}
    
    # Run sync function in thread pool to make it async
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_extract)


@tool()
async def website_crawler(data_store: Dict[str, Any], crawl_instructions: str) -> Dict[str, Any]:
    """
    Intelligently crawl websites to extract specific content based on natural language requirements.
    
    This tool automatically:
    - Extracts URLs from instructions or current context
    - Determines appropriate crawl depth and scope
    - Applies respectful crawling practices
    - Filters and organizes content as requested
    - Handles different content types and formats

    Args:
        data_store: Agent's data store containing configuration and state
        crawl_instructions: Natural language description of what to crawl and extract

    Returns:
        Dictionary with crawled content and metadata for context and output
    """
    # Preconditions (Design by Contract)
    assert data_store is not None, "data_store must be provided"
    assert isinstance(crawl_instructions, str) and crawl_instructions.strip(), "crawl_instructions must be a non-empty string"

    agent_id = data_store.get("agent_id")
    config = data_store.get("config", {})
    agent_name = config.get("name")
    logger.info(f"Running website_crawler for agent {agent_id} ({agent_name}) with instructions: {crawl_instructions[:100]}...")

    # --- Step 1: Generate search prompt and extract URLs ---
    # Create a prompt to analyze crawl instructions and extract URLs from context
    
    output_format = """\nOUTPUT IN JSON: Strict JSON format, no additional text.\n{
    "firecrawl_prompt": "Comprehensive prompt for Firecrawl extraction describing what detailed content to extract from the pages",
    "urls_to_crawl": ["list", "of", "valid", "urls", "extracted", "from", "instructions", "and", "context"],
    "pydantic_schema": {
        "field_name_1": {"type": "str", "description": "Description of what comprehensive content this field contains"},
        "field_name_2": {"type": "bool", "description": "Description of what this boolean represents"},
        "field_name_3": {"type": "int", "description": "Description of what this number represents"}
    }
}\n"""
    
    prompt_data = {
        "task": """First, understand the objective from the context and crawling instructions, then generate Firecrawl extraction parameters:

STEP 1: UNDERSTAND THE OBJECTIVE
- Analyze the crawling instructions and available context to understand what the user wants to accomplish
- Identify the specific information they need to extract from websites
- Understand the purpose and end goal of this crawling task
- Consider any previous context or conversation that might inform what data is needed

STEP 2: GENERATE EXTRACTION PARAMETERS
Based on your understanding of the objective:

1. Create a clear, concise prompt for Firecrawl that describes what to extract from the websites
2. Extract all valid URLs from both the instructions and the provided context  
3. Generate a Pydantic schema structure defining the fields to extract

The Firecrawl prompt should be:
- Comprehensive and specific about what detailed content to extract
- Request full context and complete information, not just keywords or brief summaries
- Emphasize extracting complete paragraphs, detailed descriptions, and comprehensive content
- Aligned with the understood objective
- Similar to: "Extract the complete company mission statement with full details, comprehensive information about SSO support including technical details and implementation, detailed explanation of open source status including licensing and contribution information, and complete information about Y Combinator participation including batch details and timeline."

The Pydantic schema should:
- Define field names that match what you want to extract based on the objective
- Specify appropriate types (str, bool, int, float, list)
- Include comprehensive descriptions for each field that emphasize extracting full, detailed content
- Descriptions should request complete information, full context, and detailed explanations rather than keywords
- Match the content described in the prompt and serve the end goal
- For string fields, emphasize capturing complete paragraphs, full descriptions, and comprehensive details

For URLs, intelligently extract and infer website URLs by analyzing the objective and context:

1. ANALYZE THE OBJECTIVE:
   - Understand what the user wants to accomplish from the crawling instructions
   - Identify what type of websites or content would fulfill this objective
   - Consider the domain or subject matter relevant to the task

2. DIRECT URL EXTRACTION:
   - Extract explicit URLs that start with http:// or https://
   - Include any complete website URLs mentioned in instructions or context

3. INTELLIGENT URL INFERENCE:
   - Analyze email domains and infer corresponding websites when they relate to the objective
   - Example: If objective involves researching an entity and you see "info@entityname.com", infer "https://entityname.com"
   - Look for domain patterns in email addresses that likely correspond to relevant websites
   - Consider common website patterns based on names/entities mentioned in context

4. CONTEXTUAL ANALYSIS:
   - Use entity names, organization names, product names, or any relevant identifiers from context
   - Cross-reference email domains with entities mentioned in the objective and context
   - Consider variations: www.domain.com, domain.com, domain.org, domain.net
   - Infer URLs that would logically contain the information needed for the objective

5. VALIDATION RULES:
   - EXCLUDE obvious email service providers (gmail.com, yahoo.com, outlook.com, etc.)
   - EXCLUDE generic domains that are unlikely to contain relevant information
   - ONLY include domains that logically relate to the objective and context
   - Format all URLs with https:// prefix for consistency

6. OUTPUT FORMAT:
   - Return complete, crawlable URLs starting with https://
   - Examples: https://relevantsite.com, https://www.targetdomain.org
   - Do NOT include: email addresses, mailto: links, or generic email providers

Remember: Focus on the objective - what information is needed and what websites would likely contain that information based on the context provided.

Remember: The extraction should serve the user's ultimate objective, not just blindly extract data.""",
        "crawl_instructions": crawl_instructions,
        "available_context": data_store.get("context", {}),
        "output_format": output_format,
    }
    prompt = get_prompt(prompt_data)
    model_id = config.get("ai_models", {}).get("default")
    response = await get_completion(prompt=prompt, model_id=model_id)

    # Parse the response as strict JSON
    parsed_response = extract_json_content(response) or {}

    # Extract the generated parameters
    firecrawl_prompt = parsed_response.get("firecrawl_prompt", "")
    urls_to_crawl = parsed_response.get("urls_to_crawl", [])
    pydantic_schema = parsed_response.get("pydantic_schema", {})
    
    # Validate and clean up extracted URLs
    filtered_urls = []
    for url in urls_to_crawl:
        # Skip obvious email addresses (contains @ and doesn't start with http/https)
        if "@" in url and not (url.startswith("http://") or url.startswith("https://")):
            logger.warning(f"Skipping email address: {url}")
            continue
        # Skip mailto links
        if url.startswith("mailto:"):
            logger.warning(f"Skipping mailto link: {url}")
            continue
        # Accept URLs that start with http or https
        if url.startswith("http://") or url.startswith("https://"):
            filtered_urls.append(url)
        # Accept domain-only URLs and add https:// prefix (for inferred URLs)
        elif "." in url and not url.startswith("www.") and not "@" in url:
            # Add https:// prefix to domain-only URLs
            formatted_url = f"https://{url}"
            filtered_urls.append(formatted_url)
            logger.info(f"Added https:// prefix to inferred URL: {url} -> {formatted_url}")
        # Accept www. URLs and add https:// prefix
        elif url.startswith("www."):
            formatted_url = f"https://{url}"
            filtered_urls.append(formatted_url)
            logger.info(f"Added https:// prefix to www URL: {url} -> {formatted_url}")
        else:
            logger.warning(f"Skipping invalid URL format: {url}")
    
    urls_to_crawl = filtered_urls

        # 1/ If no URLs found to crawl, return without body content
    if not urls_to_crawl:
        logger.info("No URLs found to crawl, returning empty result")
        return
     
    # --- Step 2: Check cache for existing crawled data ---
    cache_handler = DataHandler("website_crawl_cache")
    
    # Create cache keys for each URL
    url_cache_keys = []
    for url in urls_to_crawl:
        # Create a hash of the URL for consistent cache keys
        url_hash = hashlib.md5(url.encode()).hexdigest()
        url_cache_keys.append(f"url_{url_hash}")
    
    # Check if we have cached data for these URLs
    cached_data = await cache_handler.get_data_by_keys(url_cache_keys)
    
    # Create a prompt cache key based on the firecrawl prompt
    prompt_hash = hashlib.md5(firecrawl_prompt.encode()).hexdigest()
    exact_cache_key = f"prompt_{prompt_hash}_urls_{'_'.join(sorted(url_cache_keys))}"
    
    # a/ Check for exact match (same prompt + same URLs)
    exact_match = await cache_handler.get_data_by_key(exact_cache_key)
    if exact_match:
        logger.info(f"Found exact cache match for prompt and URLs, returning cached result")
        extracted_data = exact_match.get("content", {})
    else:
        # b/ Check if we have crawled these URLs before with different prompts
        if cached_data:
            logger.info(f"Found cached data for {len(cached_data)} URLs with different prompts")
            
            # Create a prompt to analyze if we can reuse existing data or need to re-crawl
            analysis_output_format = """\nOUTPUT IN JSON: Strict JSON format, no additional text.\n{
    "can_reuse_data": true,
    "needs_additional_crawl": false,
    "extracted_content": {
        "field_name_1": "actual_value_from_cached_data",
        "field_name_2": "actual_value_from_cached_data"
    },
    "reasoning": "Brief explanation of decision"
}\n"""
            
            analysis_prompt_data = {
                "task": """Analyze the existing cached crawl data and determine if it can satisfy the current extraction request.

STEP 1: ANALYZE COMPATIBILITY
Compare the current extraction requirements (prompt + schema) with the existing cached data:
- Can the required fields be extracted from the existing cached data?
- Is the cached data comprehensive enough to satisfy the current request?

STEP 2: EXTRACT OR DECIDE
If the cached data can satisfy the request:
- Set "can_reuse_data": true and "needs_additional_crawl": false
- Extract the COMPLETE, DETAILED DATA VALUES from the cached data according to the current schema
- Populate "extracted_content" with the full, comprehensive content (not brief summaries, keywords, or truncated text)
- Return the complete, detailed content that was previously crawled including full paragraphs, complete descriptions, and comprehensive information
- Extract ALL relevant information available in the cached data for each field

If the cached data cannot satisfy the request:
- Set "can_reuse_data": false and "needs_additional_crawl": true
- Set "extracted_content": {} (empty)
- Explain why in reasoning

IMPORTANT: When you can reuse data, return the COMPLETE, DETAILED CONTENT VALUES from the cached data, not brief summaries, keywords, or analysis. The extracted_content should contain the full, comprehensive data that was previously scraped from the websites. Always prefer detailed, complete information over brief summaries.""",
                "current_prompt": firecrawl_prompt,
                "current_schema": pydantic_schema,
                "existing_cached_data": {url: data.get("content", {}) for url, data in cached_data.items()},
                "output_format": analysis_output_format,
            }
            
            analysis_prompt = get_prompt(analysis_prompt_data)
            model_id = config.get("ai_models", {}).get("default")
            analysis_response = await get_completion(prompt=analysis_prompt, model_id=model_id)
            analysis_result = extract_json_content(analysis_response) or {}
            
            if analysis_result.get("can_reuse_data", False) and not analysis_result.get("needs_additional_crawl", True):
                logger.info("LLM determined we can reuse cached data without additional crawling")
                extracted_data = analysis_result.get("extracted_content", {})
                
                # Cache this result with the new prompt for future exact matches
                await cache_handler.save_data(exact_cache_key, extracted_data, datetime.now())
            else:
                logger.info("LLM determined we need to perform additional crawling")
                extracted_data = None  # Will trigger fresh crawl below
        else:
            logger.info("No cached data found for these URLs")
            extracted_data = None  # Will trigger fresh crawl below

    # --- Step 3: Execute Firecrawl extraction (if not satisfied by cache) ---
    if extracted_data is None:
        extracted_data = {}
        firecrawl_api_key = get_config("firecrawl_api_key")
        
        if firecrawl_api_key and urls_to_crawl and firecrawl_prompt and pydantic_schema:
            logger.info(f"Executing Firecrawl extraction for {len(urls_to_crawl)} URLs")
            try:
                extracted_data = await firecrawl_extract_async(
                    api_key=firecrawl_api_key,
                    urls=urls_to_crawl,
                    prompt=firecrawl_prompt,
                    schema_dict=pydantic_schema
                )
                logger.info(f"Firecrawl extraction completed: {len(extracted_data) if isinstance(extracted_data, dict) else 0} results")
                
                # Simplify data for caching (only store the actual extracted fields)
                cache_data = extracted_data
                if isinstance(extracted_data, dict) and 'data' in extracted_data:
                    cache_data = extracted_data['data']
                
                # Cache the fresh crawl results for future use
                await cache_handler.save_data(exact_cache_key, cache_data, datetime.now())
                
                # Also cache individual URL results for reuse analysis
                for i, url in enumerate(urls_to_crawl):
                    if i < len(url_cache_keys):
                        await cache_handler.save_data(url_cache_keys[i], cache_data, datetime.now())
                        
            except Exception as e:
                # 2/ If parsing/something fails, return without issue
                logger.warning(f"Firecrawl extraction failed, continuing without error: {str(e)}")
                extracted_data = {"error": str(e)}
        else:
            logger.info("Skipping Firecrawl extraction - missing requirements")
            if not firecrawl_api_key:
                logger.info("Missing firecrawl_api_key in config")
            if not firecrawl_prompt:
                logger.info("No Firecrawl prompt generated")
            if not pydantic_schema:
                logger.info("No Pydantic schema generated")

    # Structure the context with descriptive, globally-unique keys
    # Simplify extracted data to only include the actual data fields
    simplified_data = extracted_data
    if isinstance(extracted_data, dict) and 'data' in extracted_data:
        simplified_data = extracted_data['data']
    
    context = {
        "website_extracted_data": simplified_data,
    }

    # Postconditions (Design by Contract)
    assert "website_extracted_data" in context, "Context must contain 'website_extracted_data' key"

    # Return in the required format for Pancaik tools
    return {
        "values": {
            "context": context,
            "output": context,
        },
    } 