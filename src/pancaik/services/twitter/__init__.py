"""
Twitter service package for interacting with Twitter/X platform.

This package organizes all Twitter-related functionality in one cohesive structure:
- api.py: Low-level API client (both official API and non-API methods)
- client.py: High-level client with business logic
- handlers.py: Database handlers for Twitter data
- models.py: Data models and schemas
- tools/: Directory containing organized Twitter tools by functionality
  - publishing.py: Tools for publishing tweets and threads
  - indexing.py: Tools for indexing tweets from users and mentions
  - search.py: Tools for searching tweets
  - interaction.py: Tools for interacting with mentions
  - content.py: Tools for generating and verifying tweet content
"""

from .client import create_thread, create_tweet, get_latest_tweets, get_tweet, search

# Import tools to register them with the _GLOBAL_TOOLS dictionary
from .tools import content, indexing, interaction, publishing, search

__all__ = ["create_tweet", "create_thread", "get_latest_tweets", "search", "get_tweet"]
