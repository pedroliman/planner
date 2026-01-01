# Planner

A simple and intuitive Python task planner library for managing tasks and to-do lists.

## Features

- Create and manage tasks with titles and descriptions
- Mark tasks as completed or incomplete
- Organize tasks in a planner
- Filter tasks by completion status
- Track task creation and completion times

## Installation

```bash
pip install -e .
```

## Quick Start

```python
from planner import Planner, Task

# Create a planner
my_planner = Planner("My Tasks")

# Add tasks
task1 = Task("Buy groceries", "Milk, eggs, bread")
task2 = Task("Write report")

my_planner.add_task(task1)
my_planner.add_task(task2)

# Complete a task
task1.complete()

# Display the planner
print(my_planner)
```

## Usage

### Creating Tasks

```python
from planner import Task

# Create a simple task
task = Task("Task title")

# Create a task with description
task = Task("Task title", "Detailed description")
```

### Managing Tasks

```python
# Mark as completed
task.complete()

# Mark as incomplete
task.uncomplete()

# Check status
if task.completed:
    print("Task is done!")
```

### Using the Planner

```python
from planner import Planner, Task

# Create a planner
planner = Planner("Work Tasks")

# Add tasks
planner.add_task(Task("Review code"))
planner.add_task(Task("Write tests"))

# Get all tasks
all_tasks = planner.get_tasks()

# Get only completed tasks
completed = planner.get_tasks(completed=True)

# Get only pending tasks
pending = planner.get_tasks(completed=False)

# Count tasks
total = planner.count_tasks()
completed_count = planner.count_tasks(completed=True)
pending_count = planner.count_tasks(completed=False)

# Remove a task
planner.remove_task(task)
```

## Running the Example

```bash
python example.py
```

## Running Tests

```bash
python -m unittest discover tests
```

## Requirements

- Python 3.7 or higher
- No external dependencies required

## License

MIT License