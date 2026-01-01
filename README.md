# Planner

A minimalist project planner with GitHub-style tile visualization.

## Features

- **Two scheduling methods**:
  - **Paced** (default): Balances work across projects with proportional allocation and a two-week rule
  - **Frontload**: Concentrates work by completing projects sequentially
- **GitHub-style visualization**: See your schedule as a color-coded tile grid
- **Smart allocation**: Projects with more remaining work get proportionally more time (paced mode)
- **Half-day support**: Schedule 4-hour slots for smaller projects
- **Statistics comparison**: Compare both scheduling methods side-by-side
- **Key insights**: Know when you'll run out of work and how many days per week per project

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
- `-m, --method` - Scheduling method: `paced` (default, balanced) or `frontload` (concentrated)

### Examples

```bash
# Use default paced method
uv run planner plan

# Use frontload method
uv run planner plan --method frontload

# Plan 24 weeks with paced method
uv run planner plan -w 24
```

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

## Scheduling Methods

The planner supports two scheduling approaches:

### Paced Method (Default)

The paced method balances work across all projects:

1. **Proportional allocation**: Projects with more remaining days get more slots
2. **Two-week rule**: Each project must be worked on at least once every 2 weeks
3. **Urgency-based priority**: Projects that haven't been worked on recently get higher priority
4. **Even distribution**: Work is spread across the planning period

Use this when you want to maintain momentum on all projects simultaneously.

### Frontload Method

The frontload method concentrates work on one project at a time:

1. **Sequential completion**: Finish projects one at a time (ordered by remaining work)
2. **Maximum focus**: Dedicate all available time to the current project
3. **Clear progression**: See projects complete fully before starting the next

Use this when you want to minimize context switching and complete projects faster.

### Common Rules (Both Methods)

1. **4-hour slots**: Each day has 2 slots (AM and PM)
2. **Weekday scheduling**: Only Monday-Friday are scheduled
3. **Half-day support**: Projects with fractional days (e.g., 0.5) use individual slots

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