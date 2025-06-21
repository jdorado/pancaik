import importlib.util
import os
import sys
from typing import Any, Dict, Optional

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pancaik import init

# Optionally load secrets from keychain if available
KEYCHAIN_SECRETS = [
    ("ezenciel", "MONGO_CONNECTION", None),
    ("ezenciel", "ENCRYPTION_KEY", None),
    ("global", "OPENROUTER_API_KEY", None),
    ("global", "GEMINI_API_KEY", None),
    ("ezenciel", "ENCRYPTION_KEY", None),
]


def load_keychain_secrets():
    keychain_path = os.path.join(os.path.dirname(__file__), "keychain.py")
    if os.path.exists(keychain_path):
        spec = importlib.util.spec_from_file_location("keychain", keychain_path)
        keychain = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(keychain)
        if not keychain.load_secrets(KEYCHAIN_SECRETS):
            raise ValueError("Failed to load some secrets from keychain")


async def init_env(config: Optional[Dict[str, Any]] = None):
    """
    Initialize environment and database connection for scripts.
    Loads secrets, sets up config, and calls pancaik.init().
    """
    load_keychain_secrets()
    if config is None:
        config = {
            "db_connection": os.getenv("MONGO_CONNECTION", "mongodb://localhost:27017/pancaik"),
            "x_api_url": os.getenv("X_API", "http://localhost:6011/api"),
            "firecrawl_api_key": os.getenv("FIRECRAWL_API_KEY", ""),
            "twitter_consumer_key": "54BTR8j7PjAWPYFWn81iabC3L",
            "twitter_consumer_secret": "w2LrT4n2bqpQu4hYCRctggrH7hFfkVkpWU2hhNFAML95IBeIpQ",
            "twitter_bearer_token": "AAAAAAAAAAAAAAAAAAAAAATI2QEAAAAALTdiUe%2FF35XAtLHfT3327i8YfTc%3DkKmF0X9NCSKz9LuECvj6NLCu0IsX5UozvpvorweiUNNzaoZp9h",
            "twitter_api_key": "dc7b18913ea64203b5e272266ef1fcf8",
            "hubspot_client_id": "db77fcec-a655-4497-b6e3-4c786236a697",
            "hubspot_client_secret": "b9126152-3410-47a3-bb79-b2e5a9370235",
        }
    await init(config)
