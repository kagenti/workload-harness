"""Exgentic adapter for session management and task execution.

Provides high-level interface to Exgentic MCP server operations.
"""

import logging
import time
from dataclasses import dataclass
from typing import Iterator, Optional

from .config import ExgenticConfig
from .mcp_client import MCPClient

logger = logging.getLogger(__name__)


@dataclass
class SessionData:
    """Container for session data from Exgentic."""

    session_id: str
    task: str
    created_at: float


class ExgenticAdapter:
    """Adapter for accessing Exgentic benchmark sessions."""

    def __init__(self, config: ExgenticConfig):
        """Initialize Exgentic adapter.

        Args:
            config: Exgentic configuration
        """
        self.config = config
        self.mcp_client = MCPClient(config)
        self._initialized = False
        self._session_count = 0

    def initialize(self) -> None:
        """Initialize Exgentic adapter and MCP client."""
        logger.info("Initializing Exgentic adapter")
        self.mcp_client.initialize()
        self._initialized = True
        logger.info("Exgentic adapter initialized successfully")

    def shutdown(self) -> None:
        """Shutdown Exgentic adapter and MCP client."""
        if self._initialized:
            logger.info("Shutting down Exgentic adapter")
            self.mcp_client.shutdown()
            self._initialized = False

    def create_session(self, task_id: Optional[str] = None) -> SessionData:
        """Create a new benchmark session.

        Args:
            task_id: Optional task ID. If not provided, will use the first available task.

        Returns:
            SessionData containing session_id and task

        Raises:
            RuntimeError: If adapter not initialized or session creation fails
        """
        if not self._initialized:
            raise RuntimeError("Exgentic adapter not initialized. Call initialize() first.")

        logger.info(f"Creating new session{f' for task {task_id}' if task_id else ''}")
        created_at = time.time()

        try:
            session_id, task = self.mcp_client.create_session(task_id=task_id)
            
            self._session_count += 1
            logger.info(f"Created session {self._session_count}: {session_id}")

            return SessionData(
                session_id=session_id,
                task=task,
                created_at=created_at,
            )

        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise

    def evaluate_session(self, session_id: str) -> bool:
        """Evaluate a benchmark session.

        Args:
            session_id: Session identifier

        Returns:
            True if session was successful, False otherwise

        Raises:
            RuntimeError: If adapter not initialized or evaluation fails
        """
        if not self._initialized:
            raise RuntimeError("Exgentic adapter not initialized. Call initialize() first.")

        logger.info(f"Evaluating session: {session_id}")

        try:
            result = self.mcp_client.evaluate_session(session_id)
            success = result.get("success", False)
            logger.info(f"Session {session_id} evaluation: {'success' if success else 'failed'} {result}")
            return success

        except Exception as e:
            logger.error(f"Failed to evaluate session {session_id}: {e}")
            raise

    def close_session(self, session_id: str) -> None:
        """Close a benchmark session.

        Args:
            session_id: Session identifier

        Raises:
            RuntimeError: If adapter not initialized or close fails
        """
        if not self._initialized:
            raise RuntimeError("Exgentic adapter not initialized. Call initialize() first.")

        logger.info(f"Closing session: {session_id}")

        try:
            self.mcp_client.close_session(session_id)
            logger.info(f"Session {session_id} closed successfully")

        except Exception as e:
            logger.error(f"Failed to close session {session_id}: {e}")
            raise

    def get_task_ids(self) -> list[str]:
        """Get list of all available task IDs from the MCP server.

        Returns:
            List of task ID strings

        Raises:
            RuntimeError: If adapter not initialized or task listing fails
        """
        if not self._initialized:
            raise RuntimeError("Exgentic adapter not initialized. Call initialize() first.")

        logger.info("Fetching list of available tasks")
        task_ids = self.mcp_client.list_tasks()
        logger.info(f"Found {len(task_ids)} available tasks")
        return task_ids

    def iterate_sessions(self, task_ids: list[str]) -> Iterator[SessionData]:
        """Iterate over benchmark sessions for given task IDs.

        Creates sessions sequentially for each task ID, respecting max_tasks configuration.

        Args:
            task_ids: List of task IDs to process

        Yields:
            SessionData for each session
        """
        if not self._initialized:
            raise RuntimeError("Exgentic adapter not initialized. Call initialize() first.")

        max_tasks = self.config.max_tasks
        
        # Limit task_ids if max_tasks is set
        if max_tasks is not None:
            task_ids = task_ids[:max_tasks]
            logger.info(f"Processing {len(task_ids)} tasks (limited by max_tasks={max_tasks})")
        else:
            logger.info(f"Processing all {len(task_ids)} tasks")
        
        for idx, task_id in enumerate(task_ids, 1):
            try:
                logger.info(f"Creating session {idx}/{len(task_ids)} for task {task_id}")
                session_data = self.create_session(task_id=task_id)
                yield session_data

            except Exception as e:
                logger.error(f"Failed to create session {idx} for task {task_id}: {e}")
                raise


