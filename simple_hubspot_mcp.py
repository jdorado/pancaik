#!/usr/bin/env python3
"""
Simple POC: List HubSpot deals using LangChain MCP adapters
"""

import asyncio
import os
from langchain_mcp_adapters.client import MultiServerMCPClient

async def list_deals():
    token = os.getenv("HUBSPOT_ACCESS_TOKEN")
    if not token:
        print("Error: HUBSPOT_ACCESS_TOKEN not set")
        return
    
    # Setup MCP client
    client = MultiServerMCPClient({
        "hubspot": {
            "command": "npx",
            "args": ["-y", "@hubspot/mcp-server"],
            "transport": "stdio",
            "env": {
                "PRIVATE_APP_ACCESS_TOKEN": token
            }
        }
    })
    
    # Get tools and call list deals
    tools = await client.get_tools()
    print(f"Available tools: {[t.name for t in tools]}")
    
    # Call list-objects tool for deals
    for tool in tools:
        if tool.name == "hubspot-list-objects":
            print(f"Calling {tool.name} for deals...")
            try:
                result = await tool.ainvoke({
                    "objectType": "deals",
                    "limit": 5
                })
                print(f"Deals: {result}")
            except Exception as e:
                print(f"Error: {e}")
            break

if __name__ == "__main__":
    asyncio.run(list_deals()) 