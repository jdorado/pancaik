import os
import sys
import importlib.util
from typing import Optional, Dict, Any

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pancaik import init

# Optionally load secrets from keychain if available
KEYCHAIN_SECRETS = [
    ("ezenciel", "MONGO_CONNECTION", None),
    ("ezenciel", "ENCRYPTION_KEY", None),
    ("global", "OPENROUTER_API_KEY", None),
    ("global", "GEMINI_API_KEY", None),
]

def load_keychain_secrets():
    keychain_path = os.path.join(os.path.dirname(__file__), "ezenciel_agent", "keychain.py")
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
        }
    await init(config) 