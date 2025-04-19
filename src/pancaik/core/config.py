import sys
from typing import Any, Dict

from loguru import logger


# Create a function to process messages and replace newlines with tabs
def process_record(record):
    record["message"] = record["message"].replace("\n", "\t")
    return record


# Function to format module and function names
def format_names(record):
    # Format module name (use the last component or second-to-last if last is __init__)
    name_parts = record["name"].split(".")
    if len(name_parts) > 0:
        if len(name_parts) > 1 and name_parts[-1] == "__init__":
            record["short_name"] = "pancaik." + name_parts[-2]
        else:
            record["short_name"] = "pancaik." + name_parts[-1]
    else:
        record["short_name"] = "pancaik." + record["name"]

    # Hide __init__ function name
    if record["function"] == "__init__":
        record["display_function"] = ""
    else:
        record["display_function"] = "." + record["function"]

    # Format the module.function part to fit in 10 characters with padding
    if record["display_function"]:
        record["module_func"] = f"{record['short_name']}{record['display_function']}"
    else:
        record["module_func"] = record["short_name"]

    return record


# Configure loguru with a format similar to the original custom formatter
# Colors: INFO=green, DEBUG=blue, WARNING=yellow, ERROR/CRITICAL=red
# Format: timestamp level module.function | message
logger.remove()  # Remove default handler
logger.add(
    sys.stdout,
    format=("<dim>{time:YYYY-MM-DD HH:mm:ss}</dim> " "<level>{level: <8}</level> " "<cyan>{module_func: <10}</cyan> | " "{message}"),
    colorize=True,
    backtrace=True,
    diagnose=True,
    enqueue=True,
    catch=True,
)

# Custom color for INFO level
logger.level("INFO", color="<green>")

# Apply processing functions
logger = logger.patch(format_names)
logger = logger.patch(process_record)

# Global configuration dictionary
_config: Dict[str, Any] = {}


def get_config(key: str, default: Any = None) -> Any:
    """Get a configuration value."""
    return _config.get(key, default)


def set_config(key: str, value: Any) -> None:
    """Set a configuration value."""
    _config[key] = value


def update_config(config_dict: Dict[str, Any]) -> None:
    """Update multiple configuration values at once."""
    _config.update(config_dict)
