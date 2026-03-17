"""Prompt construction for Exgentic A2A Runner.

Builds prompts with session_id for agent to use with benchmark tools.
"""


def build_prompt(task: str, session_id: str) -> str:
    """Build prompt with task and session_id.

    The prompt format includes the task description and explicitly instructs
    the agent to use the provided session_id in all interactions with the
    benchmark tools.

    Args:
        task: Task description from Exgentic MCP server
        session_id: Session identifier to use for tool calls

    Returns:
        Formatted prompt string
    """
    prompt = f"""The task you are to complete is:
{task}

IMPORTANT: Use session id "{session_id}" in all your interactions with the benchmark tools.

When calling any benchmark-related tools or APIs, you MUST include the session_id parameter with the value "{session_id}". This ensures your actions are properly tracked and evaluated within the correct benchmark session."""

    return prompt


# Made with Bob