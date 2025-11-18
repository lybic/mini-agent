"""
Base storage interface for task persistence.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List
from datetime import datetime


@dataclass
class TaskData:
    """
    Data structure for task information.
    
    This class represents all the data that needs to be persisted for a task.
    """
    task_id: str
    status: str  # pending, running, finished, error, cancelled
    query: str
    max_steps: int
    final_state: Optional[str] = None
    timestamp_dir: Optional[str] = None
    execution_statistics: Optional[Dict[str, Any]] = None
    sandbox_info: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    request_data: Optional[Dict[str, Any]] = None
    finished_output: Optional[str] = None
    llm_context: Optional[List[Dict[str, Any]]] = None  # LLM conversation messages (without screenshots)
    cancel_requested: bool = False  # Flag to request task cancellation
    cancelled_at: Optional[datetime] = None  # Timestamp when cancellation was requested
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert TaskData to dictionary for serialization."""
        data = asdict(self)
        # Convert datetime objects to ISO format strings
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        if self.updated_at:
            data['updated_at'] = self.updated_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskData':
        """Create TaskData from dictionary."""
        # Convert ISO format strings back to datetime objects
        if 'created_at' in data and data['created_at']:
            if isinstance(data['created_at'], str):
                data['created_at'] = datetime.fromisoformat(data['created_at'])
        if 'updated_at' in data and data['updated_at']:
            if isinstance(data['updated_at'], str):
                data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        return cls(**data)


class TaskStorage(ABC):
    """
    Abstract base class for task storage implementations.
    
    This interface defines the contract for storing and retrieving task data.
    Implementations can provide in-memory storage or external database storage.
    """
    
    @abstractmethod
    async def create_task(self, task_data: TaskData) -> bool:
        """
        Create a new task entry.
        
        Args:
            task_data: TaskData object containing task information
            
        Returns:
            bool: True if creation was successful
        """
        pass
    
    @abstractmethod
    async def get_task(self, task_id: str) -> Optional[TaskData]:
        """
        Retrieve task data by task ID.
        
        Args:
            task_id: Unique identifier for the task
            
        Returns:
            TaskData if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update task data.
        
        Args:
            task_id: Unique identifier for the task
            updates: Dictionary of fields to update
            
        Returns:
            bool: True if update was successful
        """
        pass
    
    @abstractmethod
    async def delete_task(self, task_id: str) -> bool:
        """
        Delete a task entry.
        
        Args:
            task_id: Unique identifier for the task
            
        Returns:
            bool: True if deletion was successful
        """
        pass
    
    @abstractmethod
    async def list_tasks(self, 
                        status: Optional[str] = None,
                        limit: Optional[int] = None,
                        offset: int = 0) -> List[TaskData]:
        """
        List tasks with optional filtering.
        
        Args:
            status: Filter by task status (optional)
            limit: Maximum number of tasks to return (optional)
            offset: Number of tasks to skip (for pagination)
            
        Returns:
            List of TaskData objects
        """
        pass
    
    @abstractmethod
    async def count_active_tasks(self) -> int:
        """
        Count tasks with status 'pending' or 'running'.
        
        Returns:
            Number of active tasks
        """
        pass
    
    @abstractmethod
    async def cleanup_old_tasks(self, older_than_days: int) -> int:
        """
        Clean up old task records.
        
        Args:
            older_than_days: Delete tasks older than this many days
            
        Returns:
            Number of tasks deleted
        """
        pass
    
    async def save_finished_output(self, task_id: str, output: str) -> bool:
        """
        Save finished output for a task.
        
        Args:
            task_id: Unique identifier for the task
            output: Finished output text from the LLM
            
        Returns:
            bool: True if save was successful
        """
        return await self.update_task(task_id, {'finished_output': output})
    
    async def save_llm_context(self, task_id: str, messages: List[Dict[str, Any]]) -> bool:
        """
        Save LLM conversation context for a task.
        
        Args:
            task_id: Unique identifier for the task
            messages: List of LLM message dictionaries (without image content)
            
        Returns:
            bool: True if save was successful
        """
        return await self.update_task(task_id, {'llm_context': messages})
    
    async def get_llm_context(self, task_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieve LLM conversation context for a task.
        
        Args:
            task_id: Unique identifier for the task
            
        Returns:
            List of LLM message dictionaries if found, None otherwise
        """
        task_data = await self.get_task(task_id)
        return task_data.llm_context if task_data else None
    
    @abstractmethod
    async def request_cancel_task(self, task_id: str) -> bool:
        """
        Request cancellation of a task (stateless operation).
        
        This sets the cancel_requested flag in storage and sends notifications
        to running instances. Any API server can call this method.
        
        Args:
            task_id: Unique identifier for the task to cancel
            
        Returns:
            bool: True if the cancellation request was recorded successfully
        """
        pass
    
    @abstractmethod
    async def check_cancel_requested(self, task_id: str) -> bool:
        """
        Check if cancellation has been requested for a task.
        
        This is used by running tasks to poll for cancellation requests.
        
        Args:
            task_id: Unique identifier for the task
            
        Returns:
            bool: True if cancellation has been requested
        """
        pass
    
    async def request_cancel_all_tasks(self) -> int:
        """
        Request cancellation of all active tasks.
        
        Returns:
            int: Number of tasks marked for cancellation
        """
        active_tasks = await self.list_tasks(status='running')
        cancelled_count = 0
        for task in active_tasks:
            if await self.request_cancel_task(task.task_id):
                cancelled_count += 1
        return cancelled_count
