# Planner

A minimalist project planner with GitHub-style tile visualization.

## Features

- **Two intelligent scheduling methods**:
  - **Paced** (default): Balances work with EDD priority, continuity, proportional allocation, and two-week rule
  - **Frontload**: Completes projects sequentially in earliest-due-date order
- **EDD prioritization**: Projects with earlier deadlines get scheduled first
- **Continuity optimization**: Minimizes fragmentation by grouping 2-6 consecutive slots (1-3 days) on same project
- **Project renewals**: Auto-generate renewal projects with configurable work allocation
- **Excel import**: Import and update projects from spreadsheets with flexible column mapping
- **Enhanced visualization**: Color-coded tiles (in terminal) with month labels and intelligent spacing
- **52-week planning**: Full year planning horizon by default
- **Smart allocation**: Projects with more remaining work get proportionally more time
- **Half-day support**: Schedule 4-hour slots for smaller projects
- **Statistics comparison**: Compare both scheduling methods side-by-side
- **Key insights**: Know when you'll run out of work and how many days per week per project

**Note**: The visualization uses ANSI color codes for beautiful colored output in your terminal. Colors won't display in this README, but you'll see them when you run the tool!

## Installation

```bash
# Core installation (zero dependencies)
uv sync

# With Excel import support (optional)
uv pip install openpyxl
# OR: uv sync --extra excel
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
      "remaining_days": 15,
      "start_date": "2024-01-01",
      "renewal_days": 5
    },
    {
      "name": "Project Beta",
      "end_date": "2024-12-15",
      "remaining_days": 8
    }
  ]
}
```

**Optional fields**:
- `start_date`: When project starts (defaults to today)
- `renewal_days`: Auto-create renewal project with this many days after completion

3. Generate and view your schedule:
```bash
uv run planner plan
```

## Usage

### Commands

- `planner init` - Create a sample configuration file
- `planner plan` - Generate and display the project schedule
- `planner import <file.xlsx>` - Import or update projects from Excel file
- `planner init-import-config` - Create sample import configuration

### Options

**Plan command**:
- `-c, --config` - Path to configuration file (default: `projects.json`)
- `-w, --weeks` - Number of weeks to plan ahead (default: 52)
- `-m, --method` - Scheduling method: `paced` (default, balanced) or `frontload` (concentrated)

**Import command**:
- `--import-config` - Path to import configuration file (default: `import_config.json`)

### Examples

```bash
# Use default paced method (52 weeks)
uv run planner plan

# Use frontload method
uv run planner plan --method frontload

# Plan 24 weeks with paced method
uv run planner plan -w 24

# Import projects from Excel
uv run planner init-import-config  # Create config template
uv run planner import projects.xlsx

# Import with custom config
uv run planner import data.xlsx --import-config custom.json
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

The paced method balances work across all projects with intelligent prioritization:

1. **Continuity**: Groups consecutive work on same project (2-6 slots) to minimize fragmentation
2. **EDD priority**: Projects with earlier deadlines scheduled first
3. **Two-week rule**: Each project must be worked on at least once every 2 weeks
4. **Proportional allocation**: Projects with more remaining days get more slots
5. **Urgency-based priority**: Projects that haven't been worked on recently get higher priority
6. **Even distribution**: Work is spread across the planning period

**Priority order**: Continuity > 2-week urgency > EDD + proportionality + recency

Use this when you want to maintain momentum on all projects while making meaningful progress on each.

### Frontload Method

The frontload method concentrates work on one project at a time in deadline order:

1. **EDD ordering**: Finish projects in earliest-due-date order
2. **Sequential completion**: Complete each project fully before starting the next
3. **Maximum focus**: Dedicate all available time to the current project
4. **Clear progression**: See projects complete fully in deadline order

Use this when you want to minimize context switching and meet deadlines systematically.

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
│   ├── scheduler.py    # Scheduling algorithm with EDD and continuity
│   ├── visualization.py # Enhanced tile rendering with month labels
│   └── importer.py     # Excel import with column mapping
├── tests/
│   └── test_planner.py # 55 comprehensive tests
├── pyproject.toml
├── CLAUDE.md          # Development guide
└── README.md
```

## License

MIT