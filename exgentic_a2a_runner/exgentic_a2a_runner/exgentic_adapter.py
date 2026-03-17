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

    def create_session(self) -> SessionData:
        """Create a new benchmark session.

        Returns:
            SessionData containing session_id and task

        Raises:
            RuntimeError: If adapter not initialized or session creation fails
        """
        if not self._initialized:
            raise RuntimeError("Exgentic adapter not initialized. Call initialize() first.")

        logger.info("Creating new session")
        created_at = time.time()

        try:
            session_id, task = self.mcp_client.create_session()
            
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
            logger.info(f"Session {session_id} evaluation: {'success' if success else 'failed'}")
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

    def iterate_sessions(self) -> Iterator[SessionData]:
        """Iterate over benchmark sessions.

        Creates sessions one at a time up to max_tasks limit.

        Yields:
            SessionData for each session
        """
        if not self._initialized:
            raise RuntimeError("Exgentic adapter not initialized. Call initialize() first.")

        session_num = 0
        max_tasks = self.config.max_tasks
        
        while True:
            # Check if we've reached the limit
            if max_tasks is not None and session_num >= max_tasks:
                logger.info(f"Reached max_tasks limit: {max_tasks}")
                break

            try:
                session_data = self.create_session()
                session_num += 1
                yield session_data

            except Exception as e:
                logger.error(f"Failed to create session {session_num + 1}: {e}")
                raise


# Made with Bob