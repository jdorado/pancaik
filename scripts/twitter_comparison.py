import asyncio
import os
import json
import sys
from typing import Dict, Any, List

from init_env import init_env
from pancaik.core.agent import Agent
from pancaik.core.agent_handler import AgentHandler
from pancaik.core.config import logger, get_config
from pancaik.core.connections import ConnectionHandler
from pancaik.services.twitter.client import twitterapi
from pancaik.services.twitter import client as twitter_client


def print_sample_data(data: Any, source_name: str, max_items: int = 3):
    """Print a readable sample of the data structure."""
    print(f"\n--- {source_name} SAMPLE ---")
    if isinstance(data, list):
        print(f"Type: List with {len(data)} items")
        for i, item in enumerate(data[:max_items]):
            print(f"Item {i+1}:")
            if isinstance(item, dict):
                # Print first few keys and their types/values
                for j, (key, value) in enumerate(list(item.items())[:10]):  # Show more keys
                    if isinstance(value, str) and len(value) > 100:
                        print(f"  {key}: '{value[:100]}...' (string, truncated)")
                    else:
                        print(f"  {key}: {value} ({type(value).__name__})")
                if len(item) > 10:
                    print(f"  ... and {len(item) - 10} more keys")
            else:
                print(f"  {item} ({type(item).__name__})")
            print()
    elif isinstance(data, dict):
        print(f"Type: Dict with {len(data)} keys")
        for i, (key, value) in enumerate(list(data.items())[:15]):  # Show more keys
            if isinstance(value, str) and len(value) > 100:
                print(f"  {key}: '{value[:100]}...' (string, truncated)")
            elif isinstance(value, dict):
                print(f"  {key}: dict with {len(value)} keys")
            elif isinstance(value, list):
                print(f"  {key}: list with {len(value)} items")
            else:
                print(f"  {key}: {value} ({type(value).__name__})")
        if len(data) > 15:
            print(f"  ... and {len(data) - 15} more keys")
    else:
        print(f"Type: {type(data).__name__}")
        print(f"Value: {data}")
    print("-" * 40)


def compare_structures(data1: Any, data2: Any, data3: Any, source1_name: str, source2_name: str, source3_name: str) -> Dict[str, Any]:
    """Compare three data structures."""
    def get_basic_info(obj):
        if isinstance(obj, dict):
            return {"type": "dict", "keys": sorted(obj.keys()), "key_count": len(obj)}
        elif isinstance(obj, list):
            return {"type": "list", "length": len(obj), "first_item_type": type(obj[0]).__name__ if obj else None}
        else:
            return {"type": type(obj).__name__}
    
    info1 = get_basic_info(data1) if data1 is not None else None
    info2 = get_basic_info(data2) if data2 is not None else None
    info3 = get_basic_info(data3) if data3 is not None else None
    
    return {
        source1_name: info1,
        source2_name: info2,
        source3_name: info3
    }


async def test_get_tweet(tweet_id: str, connection_id1: str, connection_id2: str, connection_handler):
    """Test 1: GET_TWEET COMPARISON"""
    print("1. GET_TWEET COMPARISON")
    print("=" * 50)
    print(f"Fetching tweet ID: {tweet_id}")
    
    # TwitterAPI
    twitterapi_tweet = None
    test_tweets = await twitterapi.get_tweets_by_ids(tweet_ids=[tweet_id])
    if test_tweets:
        twitterapi_tweet = test_tweets[0]
        print(f"✓ TwitterAPI returned {len(test_tweets)} tweets")
    else:
        print("✗ TwitterAPI returned no tweets")
    
    # Connection 1
    twitter1 = await twitter_client.get_client(connection_id1, connection_handler)
    connection1_tweet = await twitter1.get_tweet(tweet_id)
    if connection1_tweet:
        print("✓ Connection1 returned tweet")
    else:
        print("✗ Connection1 returned no tweet")
    
    # Connection 2
    twitter2 = await twitter_client.get_client(connection_id2, connection_handler)
    connection2_tweet = await twitter2.get_tweet(tweet_id)
    if connection2_tweet:
        print("✓ Connection2 returned tweet")
    else:
        print("✗ Connection2 returned no tweet")
    
    # Show samples
    if twitterapi_tweet:
        print_sample_data(twitterapi_tweet, "TwitterAPI get_tweets_by_ids")
    if connection1_tweet:
        print_sample_data(connection1_tweet, "Connection1 get_tweet")
    if connection2_tweet:
        print_sample_data(connection2_tweet, "Connection2 get_tweet")
    
    # Compare structures
    comparison = compare_structures(twitterapi_tweet, connection1_tweet, connection2_tweet, "TwitterAPI", "Connection1", "Connection2")
    print(f"\nSTRUCTURE COMPARISON:")
    for source, info in comparison.items():
        print(f"{source}: {info}")


async def test_get_latest_tweets(username: str, connection_id1: str, connection_id2: str, connection_handler):
    """Test 2: GET_LATEST_TWEETS COMPARISON"""
    print("2. GET_LATEST_TWEETS COMPARISON")
    print("=" * 50)
    print(f"Fetching latest tweets for: {username}")
    
    # TwitterAPI
    twitterapi_latest = await twitterapi.get_user_tweets_by_limit(user_name=username, limit=3)
    if twitterapi_latest:
        print(f"✓ TwitterAPI returned {len(twitterapi_latest)} tweets")
    else:
        print("✗ TwitterAPI returned no tweets")
    
    # Connection 1
    twitter1 = await twitter_client.get_client(connection_id1, connection_handler)
    connection1_latest = await twitter1.get_latest_tweets(username)
    if connection1_latest:
        connection1_latest = connection1_latest[:3]  # Limit to 3 for comparison
        print(f"✓ Connection1 returned {len(connection1_latest)} tweets (limited to 3)")
    else:
        print("✗ Connection1 returned no tweets")
    
    # Connection 2
    twitter2 = await twitter_client.get_client(connection_id2, connection_handler)
    connection2_latest = await twitter2.get_latest_tweets(username)
    if connection2_latest:
        connection2_latest = connection2_latest[:3]  # Limit to 3 for comparison
        print(f"✓ Connection2 returned {len(connection2_latest)} tweets (limited to 3)")
    else:
        print("✗ Connection2 returned no tweets")
    
    # Show samples
    if twitterapi_latest:
        print_sample_data(twitterapi_latest, "TwitterAPI get_user_tweets_by_limit", max_items=2)
    if connection1_latest:
        print_sample_data(connection1_latest, "Connection1 get_latest_tweets", max_items=2)
    if connection2_latest:
        print_sample_data(connection2_latest, "Connection2 get_latest_tweets", max_items=2)
    
    # Compare structures
    comparison = compare_structures(twitterapi_latest, connection1_latest, connection2_latest, "TwitterAPI", "Connection1", "Connection2")
    print(f"\nSTRUCTURE COMPARISON:")
    for source, info in comparison.items():
        print(f"{source}: {info}")


async def test_search(query: str, connection_id1: str, connection_id2: str, connection_handler):
    """Test 3: SEARCH COMPARISON"""
    print("3. SEARCH COMPARISON")
    print("=" * 50)
    print(f"Searching for: '{query}'")
    
    # TwitterAPI
    twitterapi_search = await twitterapi.advanced_search(query=query, limit=3)
    if twitterapi_search:
        twitterapi_search = twitterapi_search.get('tweets', [])
        print(f"✓ TwitterAPI returned {len(twitterapi_search)} tweets from search")
    else:
        print("✗ TwitterAPI returned no search results")
    
    # Connection 1
    twitter1 = await twitter_client.get_client(connection_id1, connection_handler)
    connection1_search = await twitter1.search(query)
    if connection1_search:
        connection1_search = connection1_search[:3]  # Limit to 3 for comparison
        print(f"✓ Connection1 returned {len(connection1_search)} tweets (limited to 3)")
    else:
        print("✗ Connection1 returned no search results")
    
    # Connection 2
    twitter2 = await twitter_client.get_client(connection_id2, connection_handler)
    connection2_search = await twitter2.search(query)
    if connection2_search:
        connection2_search = connection2_search[:3]  # Limit to 3 for comparison
        print(f"✓ Connection2 returned {len(connection2_search)} tweets (limited to 3)")
    else:
        print("✗ Connection2 returned no search results")
    
    # Show samples
    if twitterapi_search:
        print_sample_data(twitterapi_search, "TwitterAPI advanced_search", max_items=2)
    if connection1_search:
        print_sample_data(connection1_search, "Connection1 search", max_items=2)
    if connection2_search:
        print_sample_data(connection2_search, "Connection2 search", max_items=2)
    
    # Compare structures
    comparison = compare_structures(twitterapi_search, connection1_search, connection2_search, "TwitterAPI", "Connection1", "Connection2")
    print(f"\nSTRUCTURE COMPARISON:")
    for source, info in comparison.items():
        print(f"{source}: {info}")


async def test_get_profile(profile_username: str, connection_id1: str, connection_id2: str, connection_handler):
    """Test 4: GET_PROFILE COMPARISON"""
    print("4. GET_PROFILE COMPARISON")
    print("=" * 50)
    print(f"Fetching profile for: {profile_username}")
    
    # TwitterAPI
    twitterapi_profile = await twitterapi.get_user_info(user_name=profile_username)
    if twitterapi_profile:
        print(f"✓ TwitterAPI returned profile")
    else:
        print("✗ TwitterAPI returned no profile")
    
    # Connection 1
    twitter1 = await twitter_client.get_client(connection_id1, connection_handler)
    connection1_profile = await twitter1.get_profile(profile_username)
    if connection1_profile:
        print(f"✓ Connection1 returned profile")
    else:
        print("✗ Connection1 returned no profile")
    
    # Connection 2
    twitter2 = await twitter_client.get_client(connection_id2, connection_handler)
    connection2_profile = await twitter2.get_profile(profile_username)
    if connection2_profile:
        print(f"✓ Connection2 returned profile")
    else:
        print("✗ Connection2 returned no profile")
    
    # Show samples
    if twitterapi_profile:
        print_sample_data(twitterapi_profile, "TwitterAPI get_user_info")
    if connection1_profile:
        print_sample_data(connection1_profile, "Connection1 get_profile")
    if connection2_profile:
        print_sample_data(connection2_profile, "Connection2 get_profile")
    
    # Compare structures
    comparison = compare_structures(twitterapi_profile, connection1_profile, connection2_profile, "TwitterAPI", "Connection1", "Connection2")
    print(f"\nSTRUCTURE COMPARISON:")
    for source, info in comparison.items():
        print(f"{source}: {info}")


async def main():
    # Check for test selection
    test_to_run = None
    if len(sys.argv) > 1:
        try:
            test_to_run = int(sys.argv[1])
            if test_to_run not in [1, 2, 3, 4]:
                print("Invalid test number. Use 1, 2, 3, or 4")
                return
        except ValueError:
            print("Invalid test number. Use 1, 2, 3, or 4")
            return
    
    await init_env()

    tweet_id = "1933493866268631381"
    connection_id1 = '682620da97235c1ddf27eecd'  # Original connection
    connection_id2 = '684bf9e7db5986c12b261293'  # Second connection
    
    # Get database and connection handler
    db = get_config("db")
    if db is None:
        raise ValueError("Database not initialized in config")
    connection_handler = ConnectionHandler(db)
    
    if test_to_run:
        print(f"=== RUNNING TEST {test_to_run} ===\n")
    else:
        print("=== TESTING ALL FOUR AREAS WITH THREE SOURCES ===\n")
    
    # Run specific test or all tests
    if test_to_run == 1 or test_to_run is None:
        await test_get_tweet(tweet_id, connection_id1, connection_id2, connection_handler)
        if test_to_run: return
        print("\n" + "=" * 70)
    
    if test_to_run == 2 or test_to_run is None:
        username = "elonmusk"
        await test_get_latest_tweets(username, connection_id1, connection_id2, connection_handler)
        if test_to_run: return
        print("\n" + "=" * 70)
    
    if test_to_run == 3 or test_to_run is None:
        query = "AI"
        await test_search(query, connection_id1, connection_id2, connection_handler)
        if test_to_run: return
        print("\n" + "=" * 70)
    
    if test_to_run == 4 or test_to_run is None:
        profile_username = "elonmusk"
        await test_get_profile(profile_username, connection_id1, connection_id2, connection_handler)
        if test_to_run: return
    
    if not test_to_run:
        print("\n" + "=" * 70)
        print("=== SUMMARY ===")
        print("Tested four main areas with three sources:")
        print("1. get_tweet - single tweet structure")
        print("2. get_latest_tweets - list of tweets structure") 
        print("3. search - list of tweets structure")
        print("4. get_profile - user profile structure")
        print("Check the sample data above to see the differences in structure and content.")
        print("\nTo run individual tests: python x.py [1|2|3|4]")

    return


if __name__ == "__main__":
    asyncio.run(main())
