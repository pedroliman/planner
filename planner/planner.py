"""Planner module for managing tasks."""

from typing import List, Optional
from .task import Task


class Planner:
    """A planner for managing tasks.
    
    Attributes:
        name: The name of the planner.
        tasks: List of tasks in the planner.
    """
    
    def __init__(self, name: str = "My Planner"):
        """Initialize a new planner.
        
        Args:
            name: The name of the planner.
        """
        self.name = name
        self.tasks: List[Task] = []
    
    def add_task(self, task: Task) -> None:
        """Add a task to the planner.
        
        Args:
            task: The task to add.
        """
        self.tasks.append(task)
    
    def remove_task(self, task: Task) -> None:
        """Remove a task from the planner.
        
        Args:
            task: The task to remove.
        
        Raises:
            ValueError: If the task is not in the planner.
        """
        self.tasks.remove(task)
    
    def get_task(self, index: int) -> Task:
        """Get a task by index.
        
        Args:
            index: The index of the task.
        
        Returns:
            The task at the specified index.
        
        Raises:
            IndexError: If the index is out of range.
        """
        return self.tasks[index]
    
    def get_tasks(self, completed: Optional[bool] = None) -> List[Task]:
        """Get tasks from the planner.
        
        Args:
            completed: If True, return only completed tasks.
                      If False, return only incomplete tasks.
                      If None, return all tasks.
        
        Returns:
            List of tasks matching the criteria.
        """
        if completed is None:
            return self.tasks.copy()
        return [task for task in self.tasks if task.completed == completed]
    
    def count_tasks(self, completed: Optional[bool] = None) -> int:
        """Count tasks in the planner.
        
        Args:
            completed: If True, count only completed tasks.
                      If False, count only incomplete tasks.
                      If None, count all tasks.
        
        Returns:
            Number of tasks matching the criteria.
        """
        return len(self.get_tasks(completed))
    
    def __str__(self) -> str:
        """Return a string representation of the planner."""
        lines = [f"=== {self.name} ==="]
        if not self.tasks:
            lines.append("No tasks yet.")
        else:
            for i, task in enumerate(self.tasks, 1):
                lines.append(f"{i}. {task}")
        lines.append(f"\nTotal: {len(self.tasks)} tasks "
                    f"({self.count_tasks(completed=True)} completed, "
                    f"{self.count_tasks(completed=False)} pending)")
        return "\n".join(lines)
