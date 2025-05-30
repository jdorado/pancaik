"""
Knowledge tools for agents.

This module provides tools for loading and managing knowledge content.
"""

import aiohttp
from typing import Any, Dict, Optional, List

from bson import ObjectId
from pymongo.collection import Collection
from pymongo.database import Database

from ..core.ai_logger import ai_logger
from ..core.config import get_config, logger
from ..tools.base import tool

# Valid image types
VALID_IMAGE_TYPES = [
    'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 
    'image/webp', 'image/bmp', 'image/svg+xml'
]

class KnowledgeHandler:
    """Handler for managing knowledge objects in the database."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize the knowledge handler.

        Args:
            db: Optional database instance. If not provided, will get from config when needed.
        """
        self._db = db

    def _ensure_db(self) -> Database:
        """Ensure we have a database connection."""
        if self._db is None:
            self._db = get_config("db")
            assert self._db is not None, "Database not initialized. Call init() first."
        return self._db

    def get_collection(self) -> Collection:
        """Get the knowledge collection."""
        return self._ensure_db().knowledge

    async def get_knowledge(self, knowledge_id: str) -> Optional[Dict[str, Any]]:
        """Get a knowledge entity by its ID."""
        assert knowledge_id, "Knowledge ID cannot be empty"
        collection = self.get_collection()
        knowledge = await collection.find_one({"_id": ObjectId(knowledge_id)})
        if not knowledge:
            logger.warning(f"Knowledge not found: {knowledge_id}")
            return None
        return knowledge

async def download_image(file_url: str, file_type: str) -> bytes:
    """Download an image from a URL and return as bytes.
    
    Args:
        file_url: The URL to download the image from
        file_type: The MIME type of the image
        
    Returns:
        The image data as bytes
        
    Raises:
        Exception: If download fails or file type is invalid
    """
    if file_type not in VALID_IMAGE_TYPES:
        raise ValueError(f"Invalid file type: {file_type}. Valid types: {VALID_IMAGE_TYPES}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as response:
                if response.status != 200:
                    raise Exception(f"Failed to download image: HTTP {response.status}")
                
                # Verify content type if provided by server
                content_type = response.headers.get('content-type', '').lower()
                if content_type and not any(valid_type in content_type for valid_type in VALID_IMAGE_TYPES):
                    logger.warning(f"Server reported content-type '{content_type}' but expected image type")
                
                image_data = await response.read()
                logger.info(f"Successfully downloaded image: {len(image_data)} bytes")
                return image_data
                
    except Exception as e:
        logger.error(f"Error downloading image from {file_url}: {str(e)}")
        raise


@tool
async def knowledge_loader(knowledge_id: str, data_store: Dict[str, Any]):
    """
    Loads knowledge by knowledge_id and adds it to the agent's context.

    Args:
        knowledge_id: The unique identifier of the knowledge to load
        data_store: Agent's data store containing configuration and state

    Returns:
        Dictionary with loaded knowledge in 'values' for context update, where context is a dict
        mapping the value of 'title' in params to the value of 'content' for text, or 'media_data' 
        with image data for images.
    """
    assert knowledge_id, "knowledge_id must be provided"
    assert data_store is not None, "data_store must be provided"
    agent_id = data_store.get("agent_id")
    account_id = data_store.get("config", {}).get("account_id")
    agent_name = data_store.get("config", {}).get("name")

    logger.info(f"Loading knowledge for agent {agent_id} with knowledge_id: {knowledge_id}")

    handler = KnowledgeHandler()
    knowledge = await handler.get_knowledge(knowledge_id)
    if knowledge is None:
        logger.warning(f"Knowledge not found for id: {knowledge_id}")
        ai_logger.warning(f"Knowledge not found for id: {knowledge_id}", agent_id, account_id, agent_name)
        return {}

    assert "params" in knowledge, "Knowledge document must have 'params' field"
    params = knowledge["params"]
    assert isinstance(params, dict), "Knowledge 'params' must be a dictionary"

    # Check if this is an image knowledge
    if "file_type" in params and "file_url" in params:
        file_type = params["file_type"]
        file_url = params["file_url"]
        
        # Validate file type early
        if file_type not in VALID_IMAGE_TYPES:
            error_msg = f"Invalid file type: {file_type}. Valid types: {VALID_IMAGE_TYPES}"
            logger.error(error_msg)
            ai_logger.warning(error_msg, agent_id, account_id, agent_name)
            return {}
        
        logger.info(f"Processing image knowledge: {file_type} from {file_url}")
        
        try:
            # Download the image
            image_data = await download_image(file_url, file_type)
            
            # Create media data structure
            generated_images: List[Dict[str, Any]] = []
            generated_images.append({
                'data': image_data,
                'mediaType': file_type
            })
            
            context = {'media_data': generated_images}
            ai_logger.result(f"Image knowledge loaded and added to context for agent {agent_id}", agent_id, account_id, agent_name)
            logger.info(f"Image knowledge loaded and added to context for agent {agent_id}")
            
        except Exception as e:
            logger.error(f"Failed to load image knowledge: {str(e)}")
            ai_logger.warning(f"Failed to load image knowledge: {str(e)}", agent_id, account_id, agent_name)
            return {}
    else:
        # Handle text-based knowledge (existing logic)
        assert "title" in params and "content" in params, "Text knowledge params must have 'title' and 'content' fields"
        
        # Build context: key = value of 'title', value = value of 'content'
        context = {params["title"]: params["content"]}
        ai_logger.result(f"Text knowledge loaded and added to context for agent {agent_id}", agent_id, account_id, agent_name)
        logger.info(f"Text knowledge loaded and added to context for agent {agent_id}")

    return {"values": {"context": context}}
