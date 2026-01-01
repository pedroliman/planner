# Planner

A minimalist project planner with GitHub-style tile visualization.

## Features

- **Project scheduling**: Automatically schedule work across multiple projects
- **GitHub-style visualization**: See your schedule as a color-coded tile grid
- **Smart allocation**: Projects with more remaining work get proportionally more time
- **Two-week rule**: Each project is worked on at least once every two weeks
- **Half-day support**: Schedule 4-hour slots for smaller projects
- **Key statistics**: Know when you'll run out of work and how many days per week per project

## Installation

```bash
# Using uv
uv sync
```

## Quick Start

1. Initialize a sample configuration:
```bash
uv run planner init
```

2. Edit `projects.json` with your projects:
```json
{
  "projects": [
    {
      "name": "Project Alpha",
      "end_date": "2024-12-31",
      "remaining_days": 15
    },
    {
      "name": "Project Beta",
      "end_date": "2024-12-15",
      "remaining_days": 8
    }
  ]
}
```

3. Generate and view your schedule:
```bash
uv run planner plan
```

## Usage

### Commands

- `planner plan` - Generate and display the project schedule
- `planner init` - Create a sample configuration file

### Options

- `-c, --config` - Path to configuration file (default: `projects.json`)
- `-w, --weeks` - Number of weeks to plan ahead (default: 12)

### Example Output

```
Planning 3 projects starting from 2024-11-01

Legend:
  ██ Project Alpha
  ██ Project Beta
  ██ Project Gamma
  ░░ Unassigned

    N D
Mon ████████████
Tue ████████████
Wed ████░░██████
Thu ██████████░░
Fri ████████████

============================================================
PROJECT STATISTICS
============================================================

📅 Work scheduled until: 2024-12-20 (Friday)
   (49 days of scheduled work)

Days per week by project:
----------------------------------------
  ██ Project Alpha         3.2 days/week  (64 slots) ✓
  ██ Project Beta          1.8 days/week  (36 slots) ✓
  ██ Project Gamma         0.6 days/week  (12 slots) ✓

Legend: ✓ = fully scheduled, ○ = partially scheduled
```

## Scheduling Algorithm

The planner uses a scheduling algorithm with the following rules:

1. **Iterate through 4-hour slots**: Each day has 2 slots (AM and PM)
2. **Proportional allocation**: Projects with more remaining days get more slots
3. **Two-week rule**: Each project must be worked on at least once every 2 weeks
4. **Urgency-based priority**: Projects that haven't been worked on recently get higher priority
5. **Weekday scheduling**: Only Monday-Friday are scheduled

## Development

### Running Tests

```bash
uv run pytest
```

### Project Structure

```
planner/
├── planner/
│   ├── __init__.py
│   ├── cli.py          # Command-line interface
│   ├── models.py       # Data models (Project, Schedule, etc.)
│   ├── scheduler.py    # Scheduling algorithm
│   └── visualization.py # Tile rendering and statistics
├── tests/
│   └── test_planner.py
├── pyproject.toml
└── README.md
```

## License

MIT