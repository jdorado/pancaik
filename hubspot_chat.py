#!/usr/bin/env python3
"""
HubSpot Chat Interface using AI Router with MCP tools
"""

import asyncio
import os
import sys
sys.path.append('src')

from langchain_mcp_adapters.client import MultiServerMCPClient
from pancaik.utils.ai_router import get_completion

async def hubspot_chat():
    """Simple HubSpot chat using AI router."""
    
    # Check token
    token = os.getenv("HUBSPOT_ACCESS_TOKEN")
    if not token:
        print("Error: Set HUBSPOT_ACCESS_TOKEN environment variable")
        return
    
    # Setup MCP client
    client = MultiServerMCPClient({
        "hubspot": {
            "command": "npx",
            "args": ["-y", "@hubspot/mcp-server"],
            "transport": "stdio",
            "env": {"PRIVATE_APP_ACCESS_TOKEN": token}
        }
    })
    
    # Get HubSpot tools
    tools = await client.get_tools()
    print(f"Connected to HubSpot with {len(tools)} tools")
    
    # Simple query
    query = "List the deals from HubSpot"
    
    print(f"\nQuery: {query}")
    
    try:
        result = await get_completion(
            prompt=query,
            tools=tools,
            agent_mode=True,
            system_message="You are a HubSpot assistant. Use the tools to answer questions.",
            verbose=True
        )
        
        print(f"\nResult: {result['final_output']}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(hubspot_chat()) 