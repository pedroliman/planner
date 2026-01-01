# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A minimalist project planner with GitHub-style tile visualization. Zero production dependencies (pure Python stdlib).

Supports two scheduling methods:
- **Paced** (default): Balances work across projects with proportional allocation and a two-week rule
- **Frontload**: Concentrates work by completing projects sequentially

## Common Commands

### Development Setup
```bash
uv sync                    # Install dependencies
```

### Running the Application
```bash
uv run planner init                      # Create sample projects.json
uv run planner plan                      # Generate and display schedule (paced method)
uv run planner plan --method frontload   # Use frontload method
uv run planner plan -w 24                # Plan for 24 weeks
```

### Testing
```bash
uv run pytest                                              # Run all tests
uv run pytest tests/test_planner.py::TestScheduler        # Run specific test class
uv run pytest tests/test_planner.py::TestScheduler::test_basic_schedule  # Run specific test
uv run pytest -v                                           # Verbose output
```

## Architecture

### Module Organization

The codebase has a clean modular structure with clear separation of concerns:

- **models.py**: Core data structures (Project, ScheduledSlot, Schedule) with ANSI color support
- **scheduler.py**: The scheduling algorithm engine (Scheduler class)
- **visualization.py**: GitHub-style tile grid rendering and statistics
- **cli.py**: Command-line interface using argparse
- **main.py**: Entry point (simple wrapper)

Data flows: JSON config → Project objects → Scheduler → Schedule → Visualization

### Scheduling Algorithms

The `scheduler.py:Scheduler` class supports two scheduling methods via `create_schedule(num_weeks, method)`:

#### Paced Method (`_create_schedule_paced`)
Default method that balances work across all projects:

1. **Proportional allocation**: Projects with more `remaining_days` get proportionally more slots
2. **Two-week rule**: Each project must be scheduled at least once every 14 calendar days (MAX_GAP_SLOTS = 28)
3. **Urgency-based selection**: `_get_most_urgent_project()` scores projects based on:
   - Time since last scheduled (prioritizes projects approaching 14-day gap)
   - Remaining work proportion (via `_calculate_weights()`)
4. **Even distribution**: Work is spread across the planning period

The scheduler iterates through time slots chronologically, selecting projects using the urgency scoring.

#### Frontload Method (`_create_schedule_frontload`)
Concentrates work by completing projects sequentially:

1. **Sequential processing**: Projects sorted by `slots_remaining` (descending)
2. **Complete before moving**: Assigns all slots to current project before starting next
3. **No two-week rule**: Projects may not be touched for weeks
4. **Minimal context switching**: Optimizes for focus on one project at a time

Both methods iterate through time slots, skip weekends, and support fractional days.

#### Common Architecture
- **4-hour slot system**: Each day has 2 slots (AM/PM), weekdays only (Mon-Fri)
- **Fractional day support**: `remaining_days` can be 0.5 for half-day (4-hour) slots
- **Method dispatching**: `create_schedule()` dispatches to the appropriate private method

### Time Slot System

- Each `ScheduledSlot` represents a 4-hour block
- Properties: `is_morning`, `is_afternoon`, `time_label` (AM/PM)
- A full workday = 2 slots
- `Project.slots_remaining` = `remaining_days * 2`
- This allows fine-grained scheduling (half-day increments)

### Configuration Format

Projects are defined in `projects.json`:
```json
{
  "projects": [
    {
      "name": "Project Name",
      "end_date": "2024-12-31",
      "remaining_days": 15  // Can be 0.5 for half-day
    }
  ]
}
```

### Visualization System

`visualization.py` renders schedules as a 7×52 grid (days of week × weeks):

- **Tile characters**: `██` (full day same project), `█▓` (split day), `░░` (unassigned)
- **Color legend**: 6-color ANSI palette assigned round-robin to projects
- **Statistics**: Per-project days/week, total slots, completion dates
- Uses Unicode block characters and ANSI color codes for terminal output

### Testing Structure

`tests/test_planner.py` has comprehensive coverage:
- **TestProject**: Slot calculations, deadline logic
- **TestScheduledSlot**: Time slot properties
- **TestSchedule**: Filtering and date operations
- **TestScheduler**: Core algorithm verification including:
  - Weekday-only scheduling
  - All work assignment
  - Proportional distribution ratios
  - Two-week rule enforcement (critical for paced method: verifies max 14-day gaps)
  - Statistics accuracy
- **TestSchedulingMethods**: Edge cases for both scheduling methods:
  - Empty project lists
  - Single project
  - Zero remaining days
  - Fractional days
  - Frontload concentration verification
  - Paced distribution verification
  - Invalid method handling
  - Too much work for schedule

When modifying scheduling methods:
- Paced method: Ensure two-week rule tests still pass (`test_schedule_two_week_rule`, `test_paced_method_distributes_work`)
- Frontload method: Ensure concentration tests pass (`test_frontload_concentrates_work`)

### CLI Behavior

When running `planner plan`:
1. **Both methods executed**: Always runs both paced and frontload scheduling
2. **Single tile view**: Shows tiles only for the selected method (default: paced)
3. **Dual statistics**: Displays statistics comparison for both methods
4. **Method selection**: Use `--method` or `-m` to choose which tiles to display

This allows users to compare both approaches while focusing visualization on their preferred method.

## Important Notes

- **No external dependencies**: Keep it that way. Use stdlib only (dataclasses, argparse, json, datetime, pathlib).
- **Date handling**: Uses `datetime.date` throughout. The scheduler starts from "today" (`date.today()`) and iterates forward.
- **Color assignment**: Projects get colors in order from `models.py:COLORS`. Wraps around if >6 projects.
- **Configuration ignored**: `projects.json` is gitignored (user-specific data).
- **Default method**: Always default to paced method for backward compatibility.
