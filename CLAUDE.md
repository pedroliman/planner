# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A minimalist project planner with GitHub-style tile visualization. Zero production dependencies (pure Python stdlib). The planner schedules work across multiple projects using a proportional allocation algorithm with a two-week rule.

## Common Commands

### Development Setup
```bash
uv sync                    # Install dependencies
```

### Running the Application
```bash
uv run planner init        # Create sample projects.json
uv run planner plan        # Generate and display schedule
uv run planner plan -w 24  # Plan for 24 weeks
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

### Scheduling Algorithm

The core scheduling logic in `scheduler.py:Scheduler` implements these rules:

1. **4-hour slot system**: Each day has 2 slots (AM/PM), weekdays only (Mon-Fri)
2. **Proportional allocation**: Projects with more `remaining_days` get proportionally more slots
3. **Two-week rule**: Each project must be scheduled at least once every 14 calendar days (MAX_GAP_SLOTS = 28)
4. **Urgency-based selection**: `_get_most_urgent_project()` scores projects based on:
   - Time since last scheduled (prioritizes projects approaching 14-day gap)
   - Remaining work proportion (via `_calculate_weights()`)
5. **Fractional day support**: `remaining_days` can be 0.5 for half-day (4-hour) slots

The scheduler iterates through time slots chronologically, selecting projects using the urgency scoring until all work is allocated.

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
  - Two-week rule enforcement (critical: verifies max 14-day gaps)
  - Statistics accuracy

When modifying the scheduler, ensure the two-week rule tests still pass (`test_two_week_rule_enforced`).

## Important Notes

- **No external dependencies**: Keep it that way. Use stdlib only (dataclasses, argparse, json, datetime, pathlib).
- **Date handling**: Uses `datetime.date` throughout. The scheduler starts from "today" (`date.today()`) and iterates forward.
- **Color assignment**: Projects get colors in order from `models.py:COLORS`. Wraps around if >6 projects.
- **Configuration ignored**: `projects.json` is gitignored (user-specific data).
