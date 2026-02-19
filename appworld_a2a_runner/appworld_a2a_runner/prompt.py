"""Prompt construction for AppWorld A2A Runner.

Builds prompts according to the exact format specified in requirements.
"""
import json
from typing import Any, Dict, Union


def serialize_supervisor(supervisor: Union[str, Dict[str, Any], None]) -> str:
    """Serialize supervisor data to string format.
    
    Args:
        supervisor: Supervisor data (string, dict, or None)
        
    Returns:
        Serialized supervisor string (empty string if None)
    """
    if supervisor is None:
        return ""
    
    if isinstance(supervisor, str):
        return supervisor
    
    if isinstance(supervisor, dict):
        # Serialize with stable key ordering and minimal pretty-print
        return json.dumps(supervisor, sort_keys=True, indent=2)
    
    # Fallback for other types
    return str(supervisor)


def build_prompt(instruction: str, supervisor: Union[str, Dict[str, Any], None], app_descriptions: dict[str, str]) -> str:
    """Build prompt according to exact specification.

    The prompt format is:

    I am your supervisor:
    {supervisor_text}

    The task you are to complete is:
    {instruction_text}

    The applications available to you to help you complete the task are the following:
    {app_descriptions}

    Args:
        instruction: Task instruction text
        supervisor: Supervisor data (string, dict, or None)
        app_descriptions: Mapping of application names to their descriptions

    Returns:
        Formatted prompt string
    """
    supervisor_text = serialize_supervisor(supervisor)
    
    prompt = f"""I am your supervisor:
{supervisor_text}

The task you are to complete is:
{instruction}

The applications available to you to help you complete the task are the following:
{str(app_descriptions)}"""
    
    return prompt

# Made with Bob
