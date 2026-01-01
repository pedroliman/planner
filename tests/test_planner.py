"""Tests for the Planner class."""

import unittest
from planner import Planner, Task


class TestPlanner(unittest.TestCase):
    """Test cases for the Planner class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.planner = Planner("Test Planner")
        self.task1 = Task("Task 1")
        self.task2 = Task("Task 2")
        self.task3 = Task("Task 3")
    
    def test_planner_creation(self):
        """Test creating a new planner."""
        planner = Planner("My Planner")
        self.assertEqual(planner.name, "My Planner")
        self.assertEqual(len(planner.tasks), 0)
    
    def test_planner_default_name(self):
        """Test planner with default name."""
        planner = Planner()
        self.assertEqual(planner.name, "My Planner")
    
    def test_add_task(self):
        """Test adding a task to the planner."""
        self.planner.add_task(self.task1)
        self.assertEqual(len(self.planner.tasks), 1)
        self.assertIn(self.task1, self.planner.tasks)
    
    def test_remove_task(self):
        """Test removing a task from the planner."""
        self.planner.add_task(self.task1)
        self.planner.remove_task(self.task1)
        self.assertEqual(len(self.planner.tasks), 0)
    
    def test_remove_task_not_in_planner(self):
        """Test removing a task that's not in the planner."""
        with self.assertRaises(ValueError):
            self.planner.remove_task(self.task1)
    
    def test_get_task(self):
        """Test getting a task by index."""
        self.planner.add_task(self.task1)
        self.planner.add_task(self.task2)
        self.assertEqual(self.planner.get_task(0), self.task1)
        self.assertEqual(self.planner.get_task(1), self.task2)
    
    def test_get_task_out_of_range(self):
        """Test getting a task with invalid index."""
        with self.assertRaises(IndexError):
            self.planner.get_task(0)
    
    def test_get_all_tasks(self):
        """Test getting all tasks."""
        self.planner.add_task(self.task1)
        self.planner.add_task(self.task2)
        tasks = self.planner.get_tasks()
        self.assertEqual(len(tasks), 2)
        self.assertIn(self.task1, tasks)
        self.assertIn(self.task2, tasks)
    
    def test_get_completed_tasks(self):
        """Test getting only completed tasks."""
        self.task1.complete()
        self.planner.add_task(self.task1)
        self.planner.add_task(self.task2)
        
        completed = self.planner.get_tasks(completed=True)
        self.assertEqual(len(completed), 1)
        self.assertIn(self.task1, completed)
    
    def test_get_incomplete_tasks(self):
        """Test getting only incomplete tasks."""
        self.task1.complete()
        self.planner.add_task(self.task1)
        self.planner.add_task(self.task2)
        
        incomplete = self.planner.get_tasks(completed=False)
        self.assertEqual(len(incomplete), 1)
        self.assertIn(self.task2, incomplete)
    
    def test_count_tasks(self):
        """Test counting all tasks."""
        self.planner.add_task(self.task1)
        self.planner.add_task(self.task2)
        self.assertEqual(self.planner.count_tasks(), 2)
    
    def test_count_completed_tasks(self):
        """Test counting completed tasks."""
        self.task1.complete()
        self.planner.add_task(self.task1)
        self.planner.add_task(self.task2)
        self.assertEqual(self.planner.count_tasks(completed=True), 1)
    
    def test_count_incomplete_tasks(self):
        """Test counting incomplete tasks."""
        self.task1.complete()
        self.planner.add_task(self.task1)
        self.planner.add_task(self.task2)
        self.assertEqual(self.planner.count_tasks(completed=False), 1)
    
    def test_planner_str_empty(self):
        """Test string representation of empty planner."""
        planner_str = str(self.planner)
        self.assertIn("Test Planner", planner_str)
        self.assertIn("No tasks yet", planner_str)
    
    def test_planner_str_with_tasks(self):
        """Test string representation of planner with tasks."""
        self.planner.add_task(self.task1)
        self.planner.add_task(self.task2)
        planner_str = str(self.planner)
        self.assertIn("Test Planner", planner_str)
        self.assertIn("Task 1", planner_str)
        self.assertIn("Task 2", planner_str)
        self.assertIn("Total: 2 tasks", planner_str)
    
    def test_add_none_task(self):
        """Test that adding None task raises ValueError."""
        with self.assertRaises(ValueError):
            self.planner.add_task(None)


if __name__ == "__main__":
    unittest.main()
