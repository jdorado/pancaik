#!/usr/bin/env python3
"""
Simple HubSpot query using MCP tools directly
"""

import asyncio
import os
from langchain_mcp_adapters.client import MultiServerMCPClient

async def query_hubspot():
    """Simple HubSpot query demonstration."""
    
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
    
    # User query
    query = "List the deals from HubSpot"
    print(f"\nQuery: {query}")
    
    # Find and use the list-objects tool for deals
    for tool in tools:
        if tool.name == "hubspot-list-objects":
            print(f"Using tool: {tool.name}")
            try:
                result = await tool.ainvoke({
                    "objectType": "deals",
                    "limit": 3
                })
                
                import json
                # Parse JSON string result
                if isinstance(result, str):
                    result = json.loads(result)
                
                print(f"\nResult: Found {len(result['results'])} deals")
                for i, deal in enumerate(result['results'], 1):
                    props = deal['properties']
                    print(f"{i}. {props.get('dealname', 'No name')} - ${props.get('amount', '0')} - {props.get('dealstage', 'No stage')}")
                
            except Exception as e:
                print(f"Error: {e}")
            break
    
    print("\n✅ This demonstrates how an LLM would use the MCP tools to answer the user's query!")

if __name__ == "__main__":
    asyncio.run(query_hubspot()) 