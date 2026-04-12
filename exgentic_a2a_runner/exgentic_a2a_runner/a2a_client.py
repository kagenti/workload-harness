"""A2A client for communicating with remote agent endpoints.

Implements the A2A protocol for sending prompts and receiving responses using JSON-RPC.
"""

import logging
import threading
import time
import uuid
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests

from .config import A2AConfig

logger = logging.getLogger(__name__)


class A2AProxyClient:
    """Client for A2A protocol communication using JSON-RPC."""

    def __init__(self, config: A2AConfig):
        """Initialize A2A client.

        Args:
            config: A2A configuration
        """
        self.config = config
        self._local = threading.local()
        
        # Fetch agent card and determine RPC URL (using temporary session)
        temp_session = self._create_session()
        try:
            self.rpc_url = self._discover_rpc_url_with_session(temp_session)
            logger.info(f"A2A client initialized with RPC URL: {self.rpc_url}")
        finally:
            temp_session.close()
    
    def _create_session(self) -> requests.Session:
        """Create a new requests session with proper configuration."""
        session = requests.Session()
        
        # Set default headers
        session.headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )
        
        # Set auth token if provided
        if self.config.auth_token:
            session.headers["Authorization"] = f"Bearer {self.config.auth_token}"
        
        return session
    
    @property
    def session(self) -> requests.Session:
        """Get thread-local session, creating one if needed."""
        if not hasattr(self._local, 'session'):
            self._local.session = self._create_session()
        return self._local.session

    def _normalize_endpoint_path(self) -> str:
        """Normalize configured endpoint path to '/path' format."""
        endpoint_path = (self.config.endpoint_path or "/").strip()
        if not endpoint_path:
            endpoint_path = "/"
        if not endpoint_path.startswith("/"):
            endpoint_path = "/" + endpoint_path
        return endpoint_path

    def _build_rpc_url(self, base_url: str) -> str:
        """Build RPC URL by appending configured endpoint path to a base URL."""
        return base_url.rstrip("/") + self._normalize_endpoint_path()

    def _get_agent_card_with_session(self, session: requests.Session) -> Dict[str, Any]:
        """Fetch the agent card from the standard discovery location.

        Args:
            session: Requests session to use

        Returns:
            Agent card as dict

        Raises:
            requests.RequestException: On network or HTTP errors
        """
        card_url = self.config.base_url.rstrip("/") + "/.well-known/agent-card.json"
        logger.debug(f"Fetching agent card from {card_url}")

        try:
            response = session.get(
                card_url,
                timeout=30,
                verify=self.config.verify_tls,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch agent card: {e}")
            raise

    def _discover_rpc_url_with_session(self, session: requests.Session) -> str:
        """Discover the JSON-RPC endpoint URL from the agent card.

        Always uses the configured base_url to build the RPC URL, ignoring
        the URL from the agent card. This ensures we use the correct URL
        when port-forwarding or proxying.

        Args:
            session: Requests session to use

        Returns:
            JSON-RPC endpoint URL
        """
        try:
            # Fetch agent card for validation, but don't use its URL
            card = self._get_agent_card_with_session(session)
            service_url = card.get("url")
            
            if service_url:
                logger.debug(f"Agent card advertises URL: {service_url}")
                logger.debug(f"Using configured base_url instead: {self.config.base_url}")
            
            # Always build RPC URL from configured base_url + endpoint path
            rpc_url = self._build_rpc_url(self.config.base_url)
            logger.debug(f"Using RPC URL: {rpc_url}")
            return rpc_url
            
        except Exception as e:
            # Fallback to configured base_url + endpoint path if card fetch fails
            logger.warning(f"Could not fetch agent card, using configured endpoint: {e}")
            return self._build_rpc_url(self.config.base_url)

    def _jsonrpc_call(
        self,
        method: str,
        params: Dict[str, Any],
        request_id: int,
    ) -> Any:
        """Make a JSON-RPC call to the agent endpoint.

        Args:
            method: JSON-RPC method name (e.g., "message/send", "tasks/get")
            params: Method parameters
            request_id: Request ID for tracking

        Returns:
            Result from the JSON-RPC response

        Raises:
            RuntimeError: On JSON-RPC error
            requests.RequestException: On network or HTTP errors
        """
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        logger.debug(f"JSON-RPC call: {method} with request_id={request_id}")

        response = self.session.post(
            self.rpc_url,
            json=payload,
            timeout=self.config.timeout_seconds,
            verify=self.config.verify_tls,
        )
        response.raise_for_status()

        data = response.json()
        if "error" in data:
            raise RuntimeError(f"JSON-RPC error: {data['error']}")

        if "result" not in data:
            raise RuntimeError(f"JSON-RPC response missing 'result' field: {data}")

        return data["result"]

    def _extract_text_from_message(self, message: Dict[str, Any]) -> str:
        """Extract text content from a message object.

        Args:
            message: Message object with role and parts

        Returns:
            Extracted text content

        Raises:
            ValueError: If message format is invalid
        """
        # Per spec, a Message has role + parts[{kind:"text", text:"..."}]
        if "parts" in message:
            parts = message["parts"]
            if isinstance(parts, list):
                text_parts = []
                for part in parts:
                    if isinstance(part, dict) and part.get("kind") == "text":
                        text = part.get("text", "")
                        if text:
                            text_parts.append(text)
                if text_parts:
                    return "\n".join(text_parts)

        # Fallback: check for direct content field
        if "content" in message:
            return str(message["content"])

        raise ValueError("Could not extract text from message")

    def _extract_text_from_task(self, task: Dict[str, Any]) -> str:
        """Extract text content from a completed task.

        Args:
            task: Task object

        Returns:
            Extracted text content

        Raises:
            ValueError: If task format is invalid or task failed
        """
        import json
        
        # Log the full task response for debugging
        logger.debug("Full task response:\n%s", json.dumps(task, indent=2, default=str))
        
        status = task.get("status", {})
        state = status.get("state")
        extracted_text = None

        # First, try to extract all possible data from artifacts (A2A spec)
        if "artifacts" in task:
            artifacts = task["artifacts"]
            if isinstance(artifacts, list) and len(artifacts) > 0:
                artifact = artifacts[0]
                if isinstance(artifact, dict) and "parts" in artifact:
                    parts = artifact["parts"]
                    if isinstance(parts, list):
                        text_parts = []
                        for part in parts:
                            if isinstance(part, dict) and part.get("kind") == "text":
                                # Allow empty strings - check for None instead
                                text = part.get("text")
                                if text is not None:
                                    text_parts.append(text)
                        # Join all text parts, even if some are empty
                        if text_parts:
                            extracted_text = "\n".join(text_parts)

        # If no artifacts, look for result in task (fallback)
        if not extracted_text and "result" in task:
            result = task["result"]
            if isinstance(result, dict):
                # Try to extract message from result
                if "message" in result:
                    try:
                        extracted_text = self._extract_text_from_message(result["message"])
                    except ValueError:
                        pass
                # Try direct text extraction
                if not extracted_text and "text" in result:
                    extracted_text = str(result["text"])
                if not extracted_text and "content" in result:
                    extracted_text = str(result["content"])
            elif isinstance(result, str):
                extracted_text = result

        # Now handle different states with extracted information
        if state == "failed":
            error = status.get("error", "Unknown error")
            if extracted_text:
                raise ValueError(f"Task failed: {error}. Output: {extracted_text}")
            else:
                raise ValueError(f"Task failed: {error}")

        if state == "canceled":
            if extracted_text:
                raise ValueError(f"Task was canceled. Partial output: {extracted_text}")
            else:
                raise ValueError("Task was canceled")

        if state == "rejected":
            if extracted_text:
                raise ValueError(f"Task was rejected. Output: {extracted_text}")
            else:
                raise ValueError("Task was rejected")

        # For completed tasks, return the extracted text (or empty string if none)
        if state == "completed":
            return extracted_text or ""
        
        # For other states without extracted text, raise error
        if extracted_text:
            return extracted_text

        raise ValueError("Could not extract text from task result")

    def send_prompt(
        self,
        prompt: str,
        poll_interval_s: float = 0.5,
        timeout_s: Optional[float] = None,
    ) -> str:
        """Send prompt to A2A endpoint and get response.

        Args:
            prompt: The prompt text to send
            poll_interval_s: Polling interval for task status (default: 0.5s)
            timeout_s: Timeout for task completion (default: config timeout)

        Returns:
            Plain text response from the agent

        Raises:
            requests.RequestException: On network or HTTP errors
            ValueError: On invalid response format
            TimeoutError: If task doesn't complete in time
            Exception: On any other error
        """
        if timeout_s is None:
            timeout_s = float(self.config.timeout_seconds)

        try:
            # Build message per A2A spec: role + parts[{kind:"text", text:"..."}]
            message = {
                "role": "user",
                "parts": [{"kind": "text", "text": prompt}],
                "messageId": str(uuid.uuid4()),
            }

            logger.debug(f"Sending message to {self.rpc_url}")

            # Send message via JSON-RPC
            result = self._jsonrpc_call(
                "message/send",
                params={"message": message, "metadata": {}},
                request_id=1,
            )

            # The server can return either a Message or a Task
            if result.get("kind") != "task":
                # It's a Message object - extract text directly
                logger.debug("Received direct message response")
                return self._extract_text_from_message(result)

            # It's a Task - poll for completion
            task_id = result["id"]
            logger.debug(f"Received task {task_id}, polling for completion")

            deadline = time.time() + timeout_s
            request_id = 2

            while time.time() < deadline:
                task = self._jsonrpc_call(
                    "tasks/get",
                    params={"id": task_id},
                    request_id=request_id,
                )
                request_id += 1

                logger.debug("Task poll response: %s", task)

                state = task.get("status", {}).get("state")
                logger.debug(f"Task {task_id} state: {state}")

                if state in {"completed", "failed", "canceled", "rejected"}:
                    return self._extract_text_from_task(task)

                time.sleep(poll_interval_s)

            raise TimeoutError(f"Task {task_id} did not finish within {timeout_s}s")

        except requests.Timeout as e:
            logger.error(f"A2A request timed out: {e}")
            raise
        except requests.RequestException as e:
            logger.error(f"A2A request failed: {type(e).__name__}: {e}")
            raise
        except Exception as e:
            logger.error(f"A2A request failed: {type(e).__name__}: {e}")
            raise


