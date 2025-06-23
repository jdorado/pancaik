#!/usr/bin/env python3
"""
Script to find agents that are using the api_request tool.

This script connects to the MongoDB database and searches for agents
that have the 'api_request' tool configured in their tools array.
"""

import asyncio
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from init_env import init_env

from pancaik.core.config import get_config, logger


async def find_agents_with_api_request_tool() -> List[Dict[str, Any]]:
    """
    Find all agents that have the api_request tool configured.
    Returns:
        List of agent documents that use the api_request tool
    """
    db = get_config("db")
    collection = db.agents
    query = {"tools": {"$elemMatch": {"id": "api_request"}}}
    agents_with_api_request = []
    async for agent in collection.find(query):
        agents_with_api_request.append(agent)
    return agents_with_api_request


async def print_agent_info(agents: List[Dict[str, Any]]) -> None:
    """
    Print information about agents using the api_request tool.

    Args:
        agents: List of agent documents
    """
    if not agents:
        print("No agents found using the api_request tool.")
        return

    print(f"Found {len(agents)} agent(s) using the api_request tool:\n")

    for i, agent in enumerate(agents, 1):
        agent_id = str(agent["_id"])
        agent_name = agent.get("name", "Unknown")
        account_id = agent.get("account_id", "Unknown")
        status = agent.get("status", "Unknown")
        is_active = agent.get("is_active", False)
        created_at = agent.get("created_at", "Unknown")

        print(f"{i}. Agent ID: {agent_id}")
        print(f"   Name: {agent_name}")
        print(f"   Account ID: {account_id}")
        print(f"   Status: {status}")
        print(f"   Active: {is_active}")
        print(f"   Created: {created_at}")

        # Find api_request tools in the tools array
        api_request_tools = []
        tools = agent.get("tools", [])
        for tool in tools:
            if isinstance(tool, dict) and tool.get("id") == "api_request":
                api_request_tools.append(tool)

        print(f"   API Request Tools ({len(api_request_tools)}):")
        for j, tool in enumerate(api_request_tools, 1):
            instance_id = tool.get("instance_id", "No instance_id")
            params = tool.get("params", {})
            print(f"     {j}. Instance ID: {instance_id}")
            if params:
                print(f"        Parameters: {params}")

        print()  # Empty line for readability


async def get_all_agents_with_tools() -> List[Dict[str, Any]]:
    """
    Get all agents and show which tools they use (for debugging).

    Returns:
        List of all agent documents with tools
    """
    db = get_config("db")
    collection = db.agents

    agents_with_tools = []
    async for agent in collection.find({"tools": {"$exists": True, "$ne": []}}):
        agents_with_tools.append(agent)

    return agents_with_tools


async def print_all_tools_summary() -> None:
    """
    Print a summary of all tools being used across all agents.
    """
    agents = await get_all_agents_with_tools()

    tool_usage = {}
    total_agents = len(agents)

    for agent in agents:
        tools = agent.get("tools", [])
        for tool in tools:
            if isinstance(tool, dict):
                tool_id = tool.get("id")
                if tool_id:
                    if tool_id not in tool_usage:
                        tool_usage[tool_id] = {"count": 0, "agents": []}
                    tool_usage[tool_id]["count"] += 1
                    tool_usage[tool_id]["agents"].append({"id": str(agent["_id"]), "name": agent.get("name", "Unknown")})

    print(f"\nTOOL USAGE SUMMARY ({total_agents} total agents with tools):")
    print("=" * 60)

    # Sort by usage count
    sorted_tools = sorted(tool_usage.items(), key=lambda x: x[1]["count"], reverse=True)

    for tool_id, usage_info in sorted_tools:
        count = usage_info["count"]
        agents_list = usage_info["agents"]

        print(f"\n{tool_id}: {count} usage(s)")
        for agent_info in agents_list:
            print(f"  - {agent_info['name']} (ID: {agent_info['id']})")


def summarize_agents_by_owner(agents: list[dict]) -> None:
    """
    Print a summary of number of agents per owner_id.
    """
    owner_counts = defaultdict(int)
    for agent in agents:
        owner_id = agent.get("owner_id", "Unknown")
        owner_counts[owner_id] += 1
    print("\nOWNER SUMMARY (number of agents per owner_id):")
    print("=" * 60)
    for owner_id, count in sorted(owner_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"{owner_id}: {count} agent(s)")


async def summarize_all_agents_by_owner():
    """
    Print a summary of all agents in the database, grouped by owner_id.
    """
    db = get_config("db")
    collection = db.agents
    agents = []
    async for agent in collection.find({}):
        agents.append(agent)
    owner_counts = defaultdict(list)
    for agent in agents:
        owner_id = agent.get("owner_id", "Unknown")
        owner_counts[owner_id].append(agent)
    print("\nALL AGENTS OWNER SUMMARY:")
    print("=" * 60)
    for owner_id, agent_list in sorted(owner_counts.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"{owner_id}: {len(agent_list)} agent(s)")
    print("\nTotal unique owners:", len(owner_counts))
    print("Total agents:", len(agents))


async def inventory_by_owner():
    """
    Prints an inventory of agents and their tools, grouped by owner_id.
    """
    db = get_config("db")
    collection = db.agents

    all_agents = []
    # Find all agents, projecting only necessary fields
    async for agent in collection.find(
        {}, {"name": 1, "owner_id": 1, "tools.id": 1, "is_active": 1, "last_run": 1}
    ):
        all_agents.append(agent)

    agents_by_owner = defaultdict(list)
    for agent in all_agents:
        owner_id = agent.get("owner_id", "Unknown")
        agents_by_owner[owner_id].append(agent)

    print("\n--- Agent Inventory by Owner ---")

    # Sort owners by owner_id for consistent output
    sorted_owners = sorted(agents_by_owner.items(), key=lambda item: str(item[0]))

    total_agents_count = 0

    for owner_id, agents in sorted_owners:
        print(f"\nOwner: {owner_id} ({len(agents)} agents)")
        print("-" * 40)
        total_agents_count += len(agents)

        # Sort agents by name
        for agent in sorted(agents, key=lambda x: x.get("name", "")):
            agent_name = agent.get("name", "Unnamed Agent")
            agent_id = agent.get("_id", "N/A")
            is_active = agent.get("is_active", False)
            last_run = agent.get("last_run", "Never")
            if last_run is None:
                last_run = "Never"

            print(
                f"  - Agent: {agent_name} (ID: {agent_id}) "
                f"| Active: {is_active} | Last Run: {last_run}"
            )

            tools = agent.get("tools", [])
            if not tools:
                print("    - No tools configured.")
            else:
                tool_names = sorted([
                    tool.get("id", "Unknown Tool")
                    for tool in tools
                    if isinstance(tool, dict)
                ])
                print(f"    - Tools: {', '.join(tool_names)}")

    print("\n" + "=" * 60)
    print(f"Total unique owners: {len(agents_by_owner)}")
    print(f"Total agents inventoried: {total_agents_count}")
    print("--- End of Inventory ---")


async def main():
    """Main function to run the script."""
    print("=== Pancaik Agent Tool/Owner Summary ===\n")
    try:
        await init_env()
        await inventory_by_owner()
        # Print all agents summary by owner
        # await summarize_all_agents_by_owner()
        # (Optional: keep the api_request tool summary below)
        # agents = await find_agents_with_api_request_tool()
        # await print_agent_info(agents)
        # print("\n" + "=" * 60)
        # await print_all_tools_summary()
        # summarize_agents_by_owner(agents)
    except Exception as e:
        logger.error(f"Error running script: {str(e)}")
        print(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
