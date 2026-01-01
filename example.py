"""Example usage of the planner library."""

from planner import Planner, Task


def main():
    """Demonstrate basic planner functionality."""
    # Create a new planner
    my_planner = Planner("Work Tasks")
    
    # Add some tasks
    task1 = Task("Review code", "Review the pull request #123")
    task2 = Task("Write documentation", "Update README with new features")
    task3 = Task("Fix bug", "Fix the login issue")
    
    my_planner.add_task(task1)
    my_planner.add_task(task2)
    my_planner.add_task(task3)
    
    # Display the planner
    print(my_planner)
    print()
    
    # Complete a task
    task1.complete()
    print("After completing task 1:")
    print(my_planner)
    print()
    
    # Show only pending tasks
    print("Pending tasks:")
    for task in my_planner.get_tasks(completed=False):
        print(f"  - {task}")
    print()
    
    # Show only completed tasks
    print("Completed tasks:")
    for task in my_planner.get_tasks(completed=True):
        print(f"  - {task}")


if __name__ == "__main__":
    main()
