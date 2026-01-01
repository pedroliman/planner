"""Task module for the planner."""

from datetime import datetime
from typing import Optional


class Task:
    """Represents a task in the planner.
    
    Attributes:
        title: The title of the task.
        description: A detailed description of the task.
        completed: Whether the task is completed.
        created_at: When the task was created.
        completed_at: When the task was completed (if completed).
    """
    
    def __init__(self, title: str, description: str = ""):
        """Initialize a new task.
        
        Args:
            title: The title of the task.
            description: Optional description of the task.
        """
        self.title = title
        self.description = description
        self.completed = False
        self.created_at = datetime.now()
        self.completed_at: Optional[datetime] = None
    
    def complete(self) -> None:
        """Mark the task as completed."""
        self.completed = True
        self.completed_at = datetime.now()
    
    def uncomplete(self) -> None:
        """Mark the task as not completed."""
        self.completed = False
        self.completed_at = None
    
    def __str__(self) -> str:
        """Return a string representation of the task."""
        status = "✓" if self.completed else " "
        return f"[{status}] {self.title}"
    
    def __repr__(self) -> str:
        """Return a detailed representation of the task."""
        return f"Task(title='{self.title}', completed={self.completed})"
