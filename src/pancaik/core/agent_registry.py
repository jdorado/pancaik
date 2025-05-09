"""
Agent registry module that centralizes agent type definitions and registration.
"""
import os
import importlib
from typing import Dict, Any
from pathlib import Path
from .agent import Agent
from .config import logger

# Global registry for agent configurations
_AGENT_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register_agent(name: str, config_template: Dict[str, Any]):
    """
    Register an agent configuration template.
    
    Args:
        name: Name for this configuration template (e.g. "twitter_indexer")
        config_template: Template configuration
    """
    assert name not in _AGENT_REGISTRY, f"Configuration {name} already registered"
    assert isinstance(config_template, dict), "Config template must be a dictionary"
    
    _AGENT_REGISTRY[name] = {
        "config_template": config_template
    }
    logger.info(f"Registered agent configuration: {name}")


def get_agent_config(name: str) -> Dict[str, Any]:
    """
    Get a configuration template.
    
    Args:
        name: The configuration template name
        
    Returns:
        Configuration template
    """
    assert name in _AGENT_REGISTRY, f"Configuration {name} not found in registry"
    return _AGENT_REGISTRY[name]["config_template"].copy()


def create_agent_instance(name: str, agent_id: str, override_config: Dict[str, Any] = None) -> Agent:
    """
    Create a new agent instance from a configuration template.
    
    Args:
        name: The configuration template name
        agent_id: Unique identifier for this instance
        override_config: Optional configuration overrides
        
    Returns:
        New agent instance
    """
    config = get_agent_config(name)
    if override_config:
        config.update(override_config)
    
    return Agent(agent_id, config)


# Load all agent configurations from Python modules
def load_agent_configurations():
    """Load all agent configurations from the agents directory."""
    agents_dir = Path(__file__).parent.parent / 'agents'
    
    if not agents_dir.exists():
        logger.warning(f"Agents directory not found: {agents_dir}")
        return

    # Add agents directory to Python path if not already there
    agents_path = str(agents_dir)
    if agents_path not in os.sys.path:
        os.sys.path.append(agents_path)
        
    for file_path in agents_dir.glob('*.py'):
        if file_path.stem == '__init__':
            continue
            
        try:
            # Import the module
            module = importlib.import_module(file_path.stem)
            
            # Get the CONFIG from the module
            if hasattr(module, 'CONFIG'):
                register_agent(file_path.stem, module.CONFIG)
            else:
                logger.warning(f"No CONFIG found in {file_path}")
                
        except Exception as e:
            logger.error(f"Error loading agent configuration from {file_path}: {e}")

# Load configurations on module import
load_agent_configurations() 