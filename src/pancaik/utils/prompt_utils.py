"""
Utility functions for handling prompts and formatting data for AI models.
"""

from typing import Dict, Any


def get_prompt(data: Dict[str, Any], wrapper_tag: str = "prompt", indent: int = 0, skip_empty: bool = True) -> str:
    """
    Converts a dictionary of key-value pairs into an XML-style prompt string.
    Handles nested dictionaries at any level automatically.
    
    Args:
        data: Dictionary containing key-value pairs to convert
        wrapper_tag: The main tag to wrap all content in (default: 'prompt')
        indent: Number of spaces to indent the content (default: 0)
        skip_empty: Whether to skip empty/None values (default: True)
        
    Returns:
        A formatted string with XML-style tags
        
    Example:
        Input: {
            'date': '2024-03-21',
            'task': 'Research task',
            'context': {
                'research': {
                    'findings': 'Some findings...',
                    'metadata': {
                        'source': 'Database A',
                        'confidence': 'High'
                    }
                },
                'analysis': 'details...'
            }
        }
        Output:
        <prompt>
            <date>
            2024-03-21
            </date>
            
            <task>
            Research task
            </task>
            
            <context>
                <research>
                    <findings>
                    Some findings...
                    </findings>
                    
                    <metadata>
                        <source>
                        Database A
                        </source>
                        
                        <confidence>
                        High
                        </confidence>
                    </metadata>
                </research>
                
                <analysis>
                details...
                </analysis>
            </context>
        </prompt>
    """
    if not data:
        return ""
        
    # Filter out empty values if skip_empty is True
    if skip_empty:
        data = {k: v for k, v in data.items() if v is not None and (not isinstance(v, dict) or v)}
        
    if not data:  # If all values were empty
        return ""
    
    # Calculate indentation
    base_indent = " " * indent
    content_indent = " " * (indent + 4)
    
    # Build the string
    lines = [f"{base_indent}<{wrapper_tag}>"]
    
    for key, value in data.items():
        # Handle nested dictionaries
        if isinstance(value, dict):
            nested_xml = get_prompt(value, key, indent + 4, skip_empty)
            if nested_xml:  # Only add if there's content
                lines.append(nested_xml)
                lines.append("")  # Add blank line after nested content
        else:
            # Convert value to string and handle multi-line values
            value_str = str(value).strip()
            if value_str:
                lines.append(f"{content_indent}<{key}>")
                # Indent each line of the value
                value_lines = value_str.split('\n')
                lines.extend(f"{content_indent}{line}" for line in value_lines)
                lines.append(f"{content_indent}</{key}>")
                lines.append("")  # Add blank line between entries
    
    # Remove the last blank line if it exists
    if lines and not lines[-1]:
        lines.pop()
    
    lines.append(f"{base_indent}</{wrapper_tag}>")
    
    return "\n".join(lines)


# We can remove format_prompt_context since dict_to_xml_string now handles nested structures 