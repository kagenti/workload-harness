"""MCP client for communicating with Exgentic MCP server.

Uses streamable HTTP transport to interact with the Exgentic benchmark server.
"""

import asyncio
import logging
import threading
from typing import Any, Dict, Optional, Tuple

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .config import ExgenticConfig

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for MCP protocol communication with Exgentic server via streamable HTTP.
    
    This client is thread-safe and maintains separate async event loops and MCP sessions
    for each thread to avoid connection conflicts.
    """

    def __init__(self, config: ExgenticConfig):
        """Initialize MCP client.

        Args:
            config: Exgentic configuration
        """
        self.config = config
        self.mcp_url = config.mcp_server_url
        self._local = threading.local()
        self._initialized = False

        logger.info(f"Initialized MCP client for {self.mcp_url}")
    
    def _get_event_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create thread-local event loop."""
        if not hasattr(self._local, 'loop'):
            self._local.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._local.loop)
        return self._local.loop
    
    def _run_async(self, coro):
        """Run async coroutine in thread-local event loop."""
        loop = self._get_event_loop()
        return loop.run_until_complete(coro)

    def initialize(self) -> None:
        """Initialize MCP client connection.

        Raises:
            RuntimeError: If connection fails
        """
        logger.info(f"Initializing MCP client for {self.mcp_url}")

        try:
            # Just verify connection works - don't keep persistent connection
            # Each thread will create its own connection when needed
            self._run_async(self._async_verify_connection())
            self._initialized = True
            logger.info("MCP client initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize MCP client: {e}")
            raise RuntimeError(f"MCP client initialization failed: {e}")

    async def _async_verify_connection(self) -> None:
        """Verify MCP server connection."""
        async with streamable_http_client(self.mcp_url) as (read, write, get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                logger.info(f"Connected to MCP server with {len(tools_result.tools)} tools available")

    def shutdown(self) -> None:
        """Shutdown MCP client connection and cleanup thread-local resources."""
        if self._initialized:
            try:
                # Close thread-local event loop if it exists
                if hasattr(self._local, 'loop'):
                    loop = self._local.loop
                    if not loop.is_closed():
                        loop.close()
                    delattr(self._local, 'loop')
                logger.info("MCP client shutdown complete")
            except Exception as e:
                logger.warning(f"Error during MCP client shutdown: {e}")
        self._initialized = False

    def list_tasks(self) -> list[str]:
        """List all available task IDs.

        Returns:
            List of task ID strings

        Raises:
            RuntimeError: If task listing fails
        """
        if not self._initialized:
            raise RuntimeError("MCP client not initialized")

        logger.info("Listing available tasks")

        try:
            tasks = self._run_async(self._async_list_tasks())
            logger.info(f"Found {len(tasks)} tasks")
            return tasks

        except Exception as e:
            logger.error(f"Failed to list tasks: {e}")
            raise RuntimeError(f"Task listing failed: {e}")

    def create_session(self, task_id: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
        """Create a new benchmark session.

        Args:
            task_id: Optional task ID. If not provided, will use the first available task.

        Returns:
            Tuple of (session_id, task_description, context)

        Raises:
            RuntimeError: If session creation fails
        """
        if not self._initialized:
            raise RuntimeError("MCP client not initialized")

        logger.info("Creating new benchmark session")

        try:
            # At this point task_id is guaranteed to be a string
            assert task_id is not None, "task_id should not be None"
            result = self._run_async(self._async_create_session(task_id))
            session_id = result["session_id"]
            task = result.get("task", result.get("task_description", ""))
            context = result.get("context")
            
            logger.info(f"Created session {session_id} for task {task_id}")
            return session_id, task, context

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
            result = self._run_async(self._async_evaluate_session(session_id))
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

    def delete_session(self, session_id: str) -> None:
        """Delete a benchmark session.

        Args:
            session_id: Session ID to delete

        Raises:
            RuntimeError: If session deletion fails
        """
        if not self._initialized:
            raise RuntimeError("MCP client not initialized")

        logger.info(f"Deleting session {session_id}")

        try:
            self._run_async(self._async_delete_session(session_id))
            logger.info(f"Session {session_id} deleted")

        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            raise RuntimeError(f"Session deletion failed: {e}")

    async def _async_delete_session(self, session_id: str) -> None:
        """Async session deletion."""
        result = None
        try:
            async with streamable_http_client(self.mcp_url) as (read, write, get_session_id):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    # Call delete_session tool
                    result = await session.call_tool(
                        "delete_session",
                        arguments={"session_id": session_id}
                    )
        except BaseExceptionGroup:  # type: ignore[misc]
            # anyio's TaskGroup wraps background task exceptions in BaseExceptionGroup
            # This occurs when the GET SSE stream fails (e.g., session already cleaned up server-side)
            # The delete_session call has already completed at this point, so we ignore it.
            pass

        # Check if the operation was successful
        if result is None or not result.content:
            raise RuntimeError("Empty response from delete_session")

        # Check if it's an error response
        if result.isError:
            content = result.content[0]
            error_msg = content.text if hasattr(content, 'text') else str(content)
            raise RuntimeError(f"Failed to delete session: {error_msg}")

        # Verify success response
        content = result.content[0]
        if hasattr(content, 'text'):
            import json
            response = json.loads(content.text)
            status = response.get("status", "")
            if status != "success":
                # Treat "already closed" or "not found" as success — evaluate_session
                # may have already closed the underlying session before delete is called.
                error_msg = response.get("error", "")
                if "client has been closed" in error_msg or "No session found" in error_msg:
                    logger.debug(f"Session {session_id} already cleaned up: {error_msg}")
                    return
                raise RuntimeError(f"Session deletion failed: {response}")

