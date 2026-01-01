"""Tests for the Task class."""

import unittest
from datetime import datetime
from planner import Task


class TestTask(unittest.TestCase):
    """Test cases for the Task class."""
    
    def test_task_creation(self):
        """Test creating a new task."""
        task = Task("Test task")
        self.assertEqual(task.title, "Test task")
        self.assertEqual(task.description, "")
        self.assertFalse(task.completed)
        self.assertIsInstance(task.created_at, datetime)
        self.assertIsNone(task.completed_at)
    
    def test_task_creation_with_description(self):
        """Test creating a task with description."""
        task = Task("Test task", "This is a test")
        self.assertEqual(task.title, "Test task")
        self.assertEqual(task.description, "This is a test")
    
    def test_task_complete(self):
        """Test completing a task."""
        task = Task("Test task")
        task.complete()
        self.assertTrue(task.completed)
        self.assertIsInstance(task.completed_at, datetime)
    
    def test_task_uncomplete(self):
        """Test uncompleting a task."""
        task = Task("Test task")
        task.complete()
        task.uncomplete()
        self.assertFalse(task.completed)
        self.assertIsNone(task.completed_at)
    
    def test_task_str(self):
        """Test string representation of task."""
        task = Task("Test task")
        self.assertIn("Test task", str(task))
        self.assertIn("[ ]", str(task))
        
        task.complete()
        self.assertIn("Test task", str(task))
        self.assertIn("[✓]", str(task))
    
    def test_task_repr(self):
        """Test repr of task."""
        task = Task("Test task")
        repr_str = repr(task)
        self.assertIn("Task", repr_str)
        self.assertIn("Test task", repr_str)
        self.assertIn("completed=False", repr_str)


if __name__ == "__main__":
    unittest.main()
