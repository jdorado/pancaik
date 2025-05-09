# Creating Custom Tools

Tools in Pancaik are functions that can be used by agents to perform specific tasks. This guide will walk you through creating your own custom tools that can be integrated with Pancaik agents.

## Understanding Tools in Pancaik

Tools are asynchronous functions that are registered globally through a decorator, making them accessible to any agent in the system. They follow a consistent pattern:

1. They are decorated with the `@tool` decorator
2. They are asynchronous functions (defined with `async def`)
3. They typically take a `data_store` parameter for sharing data between tools
4. They return a dictionary with results and optional shared values

## Tool Return Values

Tools should return a dictionary with the following structure:

```python
{
    "status": "success",  # or "error", "no_results", etc.
    "values": {  # Optional values to share in data_store
        "context": {  # Optional context that will be auto-indexed if key exists
            "key": "value"  # e.g. "research": "research results..."
        },
        "output": {  # Optional outputs that will be timestamped
            "key": "value"  # e.g. "selected_topic": {"title": "Topic 1"}
        }
    }
}
```

### Values Dictionary Structure

The `values` dictionary in the return object has two special keys:

1. `context`: Used for accumulating context. If a key already exists, it will be auto-indexed (e.g. research, research_2, etc.)
   - Example: Research results, web search results, etc.
   - Each value is stored with metadata (timestamp, tool_id)

2. `output`: Used for outputs that need tracking
   - Example: Selected topics, generated content, etc.
   - Each value is stored with metadata (timestamp, tool_id)

## Basic Tool Structure

Here's the basic structure of a Pancaik tool:

```python
from typing import Dict, Any
from ...tools.base import tool

@tool
async def my_custom_tool(parameter1: str, data_store: Dict[str, Any], optional_param: int = 10):
    """
    Description of what the tool does.
    
    Args:
        parameter1: Description of first parameter
        data_store: Agent's data store containing configuration and state
        optional_param: Description of optional parameter with default value
        
    Returns:
        Dictionary with operation results and optional values
    """
    # Preconditions
    assert parameter1, "parameter1 must be provided"
    
    # Your tool logic goes here
    result = f"Processed {parameter1} with value {optional_param}"
    
    # Return dictionary with results and values to share
    return {
        "status": "success",
        "result": result,
        "values": {
            "context": {
                "processed_data": result  # Will be auto-indexed if key exists
            },
            "output": {
                "final_result": result  # Will be stored with timestamp
            }
        }
    }
```

## Sharing Data Between Tools

The `data_store` parameter is a dictionary that is passed between tools in a pipeline. To share data with other tools:

1. Include a `values` key in your return dictionary
2. Use `context` for accumulating data that will be concatenated
3. Use `output` for final results that need timestamp tracking
4. These values will be automatically added to the agent's `data_store`

## Real-World Example: Research Tool

Here's a simplified version of a research tool:

```python
@tool
async def research_topic(topic: str, data_store: Dict[str, Any]):
    """
    Researches a topic and returns findings.
    
    Args:
        topic: Topic to research
        data_store: Agent's data store containing configuration and state
        
    Returns:
        Dictionary with research results
    """
    # Research logic here...
    research_result = "Research findings..."
    
    return {
        "status": "success",
        "values": {
            "context": {
                "research": research_result  # Will be concatenated with other research
            },
            "output": {
                "topic_research": {  # Will be tracked with timestamp
                    "topic": topic,
                    "findings": research_result
                }
            }
        }
    }
```

## Tool Organization

Tools are typically organized by service or functionality. For example:

- Twitter-related tools are in `src/pancaik/services/twitter/tools.py`
- Database-related tools might be in `src/pancaik/services/database/tools.py`

## Best Practices for Tool Development

### 1. Follow Design by Contract Principles

Always add assertions to validate:
- Preconditions: What must be true before the function executes
- Postconditions: What must be true after the function executes
- Invariants: What must remain true throughout the function execution

```python
@tool
async def example_tool(parameter: str, data_store: Dict[str, Any]):
    # Preconditions
    assert parameter, "Parameter must be provided"
    assert "config" in data_store, "Config must be in the data store"
    
    # Function logic
    result = process_data(parameter)
    
    # Postconditions
    assert result is not None, "Result must not be None"
    
    return {"status": "success", "result": result}
```

### 2. Provide Comprehensive Documentation

Always include detailed docstrings that explain:
- What the tool does
- Parameters with descriptions
- Return value structure
- Any side effects

### 3. Handle Errors Gracefully

Use try/except blocks to catch and handle errors:

```python
@tool
async def safe_tool(parameter: str, data_store: Dict[str, Any]):
    try:
        # Tool logic
        result = process_data(parameter)
        return {
            "status": "success",
            "result": result
        }
    except Exception as e:
        logger.error(f"Error in safe_tool: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }
```

### 4. Use Logging

Import and use the logger from config:

```python
from ...core.config import logger

@tool
async def logging_tool(parameter: str, data_store: Dict[str, Any]):
    logger.info(f"Starting processing of {parameter}")
    # Tool logic
    logger.debug("Processing complete")
    return {"status": "success"}
```

## Real-World Example: Twitter Tool

Here's a simplified version of the `index_user_tweets` tool from the Twitter service:

```python
@tool
async def index_user_tweets(twitter_handle: str, data_store: Dict[str, Any], max_tweets: int = 100):
    """
    Indexes tweets from a specific user for searching later.
    
    Args:
        twitter_handle: Twitter handle/username to index
        data_store: Agent's data store containing configuration and state
        max_tweets: Maximum number of tweets to fetch (default: 100)
        
    Returns:
        Dictionary with indexing operation results
    """
    # Preconditions
    assert twitter_handle, "Twitter handle must be provided"
    assert max_tweets > 0, "max_tweets must be positive"
    
    # Extract credentials from data_store
    credentials = data_store.get("config", {}).get("twitter", {}).get("credentials", {})
    assert credentials, "Twitter credentials must be in the agent's data store"
    
    try:
        # Fetch and index tweets
        handler = TwitterHandler()
        tweets = await client.get_latest_tweets(credentials, twitter_handle, max_tweets=max_tweets)
        
        if tweets:
            # Store tweets in database
            await handler.insert_tweets(tweets)
            
            result = {
                "status": "success",
                "indexed_count": len(tweets),
                "values": {
                    "twitter_handle": twitter_handle,
                    "indexed_tweets_count": len(tweets)
                }
            }
        else:
            result = {
                "status": "no_tweets_found",
                "indexed_count": 0
            }
            
        return result
        
    except Exception as e:
        logger.error(f"Error indexing tweets: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "indexed_count": 0
        }
```

## Integrating Tools with Agents

Once you've created a tool, you can use it in agent task pipelines:

```yaml
tasks:
  analyze_twitter_user:
    description: "Analyze a Twitter user's recent tweets"
    pipeline:
      - index_user_tweets
      - analyze_sentiment
      - generate_report
```

The agent will execute the tools in the order specified in the pipeline, with each tool's shared values being passed to the next tool via the data_store.

## Testing Your Tools

It's recommended to write tests for your tools to ensure they work as expected:

```python
import pytest

@pytest.mark.asyncio
async def test_my_custom_tool():
    # Setup
    data_store = {"config": {...}}
    
    # Execute
    result = await my_custom_tool("test_param", data_store)
    
    # Assert
    assert result["status"] == "success"
    assert "processed_value" in result["values"]
```

## Conclusion

By following these guidelines, you can create powerful, reusable tools that integrate seamlessly with Pancaik agents. Remember to:

1. Use the `@tool` decorator
2. Make functions asynchronous
3. Include `data_store` parameter
4. Follow design by contract principles
5. Return a dictionary with results and shared values
6. Organize tools by service or functionality
7. Write comprehensive documentation and tests 