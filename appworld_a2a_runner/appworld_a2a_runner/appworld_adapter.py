"""AppWorld adapter for task enumeration and data extraction.

Provides interface to AppWorld dataset without using AppWorld's evaluation system.
"""
import logging
from typing import Any, Iterator, List

from appworld import AppWorld, load_task_ids
from appworld.task import Task

from .config import AppWorldConfig

logger = logging.getLogger(__name__)


class TaskData:
    """Container for task data extracted from AppWorld."""
    
    def __init__(self, task_id: str, instruction: str, supervisor: Any, app_descriptions: dict[str, str]):
        """Initialize task data.
        
        Args:
            task_id: Unique task identifier
            instruction: Task instruction text
            supervisor: Supervisor data (string, dict, or other)
            app_descriptions: High level description of the apps available to interact with
        """
        self.task_id = task_id
        self.instruction = instruction
        self.supervisor = supervisor
        self.app_descriptions = app_descriptions


class AppWorldAdapter:
    """Adapter for accessing AppWorld tasks without evaluation."""
    
    def __init__(self, config: AppWorldConfig):
        """Initialize AppWorld adapter.
        
        Args:
            config: AppWorld configuration
        """
        self.config = config
        self._initialized = False
    
    def initialize(self) -> None:
        """Initialize AppWorld adapter."""
        logger.info(f"Initializing AppWorld adapter with dataset: {self.config.dataset}")
        if not self.config.remote_apis_url:
            raise ValueError("APPWORLD_REMOTE_APIS_URL environment variable is required")
        
        # Note: AppWorld uses load_task_ids() for dataset enumeration
        # Individual tasks are loaded on-demand using Task.load()
        # No global AppWorld instance is needed for task enumeration
        
        self._initialized = True
        logger.info("AppWorld adapter initialized successfully")
    
    def get_task_ids(self) -> List[str]:
        """Get list of task IDs for the configured dataset.
        
        Returns:
            List of task IDs
        """
        if not self._initialized:
            raise RuntimeError("AppWorld adapter not initialized. Call initialize() first.")
        
        # Load task IDs from AppWorld dataset
        logger.info(f"Loading task IDs from dataset: {self.config.dataset}")
        task_ids = load_task_ids(dataset_name=self.config.dataset)
        
        # Apply max_tasks limit if configured
        if self.config.max_tasks is not None:
            task_ids = task_ids[:self.config.max_tasks]
            logger.info(f"Limited to {len(task_ids)} tasks (MAX_TASKS={self.config.max_tasks})")
        else:
            logger.info(f"Found {len(task_ids)} tasks in dataset")
        
        return task_ids
    
    def get_task_data(self, task_id: str) -> TaskData:
        """Extract task data from AppWorld.
        
        Args:
            task_id: Task identifier
            
        Returns:
            TaskData containing instruction and supervisor
            
        Raises:
            Exception: If task cannot be loaded or data is missing
        """
        if not self._initialized:
            raise RuntimeError("AppWorld adapter not initialized. Call initialize() first.")
        
        logger.debug(f"Loading task data for: {task_id}")
        
        # Load task using Task.load()
        task = Task.load(task_id, load_ground_truth=False)
        
        # Extract instruction
        instruction = task.instruction
        if not instruction:
            raise ValueError(f"Task {task_id} has no instruction")
        
        # Extract supervisor (may be string, dict, or None)
        supervisor = getattr(task, "supervisor", None)
        
        logger.debug(f"Task {task_id}: instruction length={len(instruction)}, "
                    f"supervisor type={type(supervisor).__name__}")
        
        # Capture app_descriptions before closing to avoid use-after-close
        app_descriptions = task.app_descriptions

        # Close the task to free resources
        task.close()
        return TaskData(
            task_id=task_id,
            instruction=instruction,
            supervisor=supervisor,
            app_descriptions=app_descriptions,
        )
    
    def iterate_tasks(self) -> Iterator[TaskData]:
        """Iterate over all tasks in the dataset.
        
        Yields:
            TaskData for each task
        """
        task_ids = self.get_task_ids()

        for task_id in task_ids:
            try:
                with AppWorld(task_id=task_id, remote_apis_url=self.config.remote_apis_url) as world:
                    yield self.get_task_data(task_id)
                    world.save_state()
                    world.save_logs()
            except Exception as e:
                logger.error(f"Failed to load task {task_id}: {e}")
                raise

# Made with Bob
