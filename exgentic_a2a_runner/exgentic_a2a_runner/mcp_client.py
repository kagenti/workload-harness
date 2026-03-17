"""MCP client for communicating with Exgentic MCP server.

Uses streamable HTTP transport to interact with the Exgentic benchmark server.
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Tuple

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .config import ExgenticConfig

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for MCP protocol communication with Exgentic server via streamable HTTP."""

    def __init__(self, config: ExgenticConfig):
        """Initialize MCP client.

        Args:
            config: Exgentic configuration
        """
        self.config = config
        self.mcp_url = config.mcp_server_url
        self.session: Optional[ClientSession] = None
        self._initialized = False

        logger.info(f"Initialized MCP client for {self.mcp_url}")

    def initialize(self) -> None:
        """Initialize MCP client connection.

        Raises:
            RuntimeError: If connection fails
        """
        logger.info(f"Initializing MCP client for {self.mcp_url}")

        try:
            # Run async initialization
            asyncio.run(self._async_initialize())
            self._initialized = True
            logger.info("MCP client initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize MCP client: {e}")
            raise RuntimeError(f"MCP client initialization failed: {e}")

    async def _async_initialize(self) -> None:
        """Async initialization of MCP client."""
        # Create streamable HTTP client
        async with streamable_http_client(self.mcp_url) as (read, write, get_session_id):
            async with ClientSession(read, write) as session:
                self.session = session
                
                # Initialize the session
                await session.initialize()
                
                # List available tools to verify connection
                tools_result = await session.list_tools()
                logger.info(f"Connected to MCP server with {len(tools_result.tools)} tools available")

    def shutdown(self) -> None:
        """Shutdown MCP client connection."""
        if self._initialized:
            try:
                # Session cleanup is handled by context managers
                logger.info("MCP client shutdown complete")
            except Exception as e:
                logger.warning(f"Error during MCP client shutdown: {e}")
        self._initialized = False

    def create_session(self, task_id: Optional[str] = None) -> Tuple[str, str]:
        """Create a new benchmark session.

        Args:
            task_id: Optional task ID. If not provided, will use the first available task.

        Returns:
            Tuple of (session_id, task_description)

        Raises:
            RuntimeError: If session creation fails
        """
        if not self._initialized:
            raise RuntimeError("MCP client not initialized")

        logger.info("Creating new benchmark session")

        try:
            # If no task_id provided, list tasks and use the first one
            if task_id is None:
                tasks = asyncio.run(self._async_list_tasks())
                if not tasks:
                    raise RuntimeError("No tasks available")
                # tasks is a list of task ID strings, not dicts
                task_id = tasks[0]
                logger.info(f"Using first available task: {task_id}")
            
            # At this point task_id is guaranteed to be a string
            assert task_id is not None, "task_id should not be None"
            result = asyncio.run(self._async_create_session(task_id))
            session_id = result["session_id"]
            task = result.get("task", result.get("task_description", ""))
            
            logger.info(f"Created session {session_id} for task {task_id}")
            return session_id, task

        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise RuntimeError(f"Session creation failed: {e}")

    async def _async_list_tasks(self) -> list:
        """Async task listing."""
        async with streamable_http_client(self.mcp_url) as (read, write, get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # Call list_tasks tool
                result = await session.call_tool("list_tasks", arguments={})
                
                if not result.content:
                    raise RuntimeError("Empty response from list_tasks")
                
                # Extract result from content
                content = result.content[0]
                if hasattr(content, 'text'):
                    import json
                    data = json.loads(content.text)
                    # tasks is a list of task ID strings
                    return data.get("tasks", [])
                else:
                    raise RuntimeError(f"Unexpected content type: {type(content)}")

    async def _async_create_session(self, task_id: str) -> Dict[str, Any]:
        """Async session creation."""
        async with streamable_http_client(self.mcp_url) as (read, write, get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # Call create_session tool with task_id
                result = await session.call_tool("create_session", arguments={"task_id": task_id})
                
                if not result.content:
                    raise RuntimeError("Empty response from create_session")
                
                # Check if it's an error response
                if result.isError:
                    content = result.content[0]
                    error_msg = content.text if hasattr(content, 'text') else str(content)
                    raise RuntimeError(f"MCP tool error: {error_msg}")
                
                # Extract result from content
                content = result.content[0]
                if hasattr(content, 'text'):
                    import json
                    return json.loads(content.text)
                else:
                    raise RuntimeError(f"Unexpected content type: {type(content)}")

    def evaluate_session(self, session_id: str) -> Dict[str, Any]:
        """Evaluate a benchmark session.

        Args:
            session_id: Session ID to evaluate

        Returns:
            Evaluation results

        Raises:
            RuntimeError: If evaluation fails
        """
        if not self._initialized:
            raise RuntimeError("MCP client not initialized")

        logger.info(f"Evaluating session {session_id}")

        try:
            result = asyncio.run(self._async_evaluate_session(session_id))
            logger.info(f"Session {session_id} evaluation complete")
            return result

        except Exception as e:
            logger.error(f"Failed to evaluate session {session_id}: {e}")
            raise RuntimeError(f"Session evaluation failed: {e}")

    async def _async_evaluate_session(self, session_id: str) -> Dict[str, Any]:
        """Async session evaluation."""
        async with streamable_http_client(self.mcp_url) as (read, write, get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # Call evaluate_session tool
                result = await session.call_tool(
                    "evaluate_session",
                    arguments={"session_id": session_id}
                )
                
                if not result.content:
                    raise RuntimeError("Empty response from evaluate_session")
                
                # Extract result from content
                content = result.content[0]
                if hasattr(content, 'text'):
                    import json
                    return json.loads(content.text)
                else:
                    raise RuntimeError(f"Unexpected content type: {type(content)}")

    def close_session(self, session_id: str) -> None:
        """Close a benchmark session.

        Args:
            session_id: Session ID to close

        Raises:
            RuntimeError: If session closure fails
        """
        if not self._initialized:
            raise RuntimeError("MCP client not initialized")

        logger.info(f"Closing session {session_id}")

        try:
            asyncio.run(self._async_close_session(session_id))
            logger.info(f"Session {session_id} closed")

        except Exception as e:
            logger.error(f"Failed to close session {session_id}: {e}")
            raise RuntimeError(f"Session closure failed: {e}")

    async def _async_close_session(self, session_id: str) -> None:
        """Async session closure."""
        async with streamable_http_client(self.mcp_url) as (read, write, get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # Call close_session tool
                await session.call_tool(
                    "close_session",
                    arguments={"session_id": session_id}
                )

# Made with Bob
