# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A minimalist project planner with GitHub-style tile visualization. Zero production dependencies (pure Python stdlib), with optional Excel import support.

Supports two scheduling methods:
- **Paced** (default): Balances work across projects with EDD priority, continuity, proportional allocation, and a two-week rule
- **Frontload**: Concentrates work by completing projects sequentially in EDD order

Key features:
- **EDD Prioritization**: Projects prioritized by earliest due date
- **Continuity**: Minimizes fragmentation by grouping consecutive work on same project (2-6 slots/1-3 days)
- **Renewals**: Projects can auto-renew with specified work allocation
- **52-week planning**: Default one-year planning horizon
- **Excel import**: Update projects from spreadsheets with configurable column mapping

## Common Commands

### Development Setup
```bash
uv sync                         # Install dependencies (core)
uv pip install openpyxl         # Install Excel support (optional)
# OR: uv sync --extra excel
```

### Running the Application
```bash
uv run planner init                      # Create sample projects.json
uv run planner plan                      # Generate and display schedule (paced, 52 weeks)
uv run planner plan --method frontload   # Use frontload method
uv run planner plan -w 24                # Plan for 24 weeks (default is 52)

# Excel import commands
uv run planner init-import-config        # Create sample import_config.json
uv run planner import projects.xlsx      # Import/update from Excel file
uv run planner import data.xlsx --import-config custom_config.json  # Custom config
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
- **scheduler.py**: The scheduling algorithm engine (Scheduler class) with EDD and continuity
- **visualization.py**: GitHub-style tile grid rendering with month labels and spacing
- **importer.py**: Excel import functionality with configurable column mapping (optional)
- **cli.py**: Command-line interface using argparse
- **main.py**: Entry point (simple wrapper)

Data flows:
- Normal: JSON config → Project objects → Scheduler → Schedule → Visualization
- Import: Excel → importer → JSON config → (same as above)

### Scheduling Algorithms

The `scheduler.py:Scheduler` class supports two scheduling methods via `create_schedule(num_weeks, method)`:

#### Paced Method (`_create_schedule_paced`)
Default method that balances work across all projects with smart prioritization:

1. **Continuity priority**: Continue current project for 2-6 consecutive slots (1-3 days) to minimize fragmentation
   - Bonus formula: `max(0, 1.0 - consecutive_slots * 0.15)`
   - Decreases as consecutive_slots increase, preventing monopolization
   - Resets on weekends and project switches
2. **Two-week rule**: Each project must be scheduled at least once every 14 calendar days (MAX_GAP_SLOTS = 28)
3. **EDD (Earliest Due Date)**: Projects with earlier `end_date` prioritized
4. **Proportional allocation**: Projects with more `remaining_days` get proportionally more slots
5. **Urgency-based selection**: `_get_most_urgent_project()` combines all factors:
   - Continuity bonus (highest priority when active)
   - Time since last scheduled (urgency)
   - EDD score (normalized by days until deadline)
   - Remaining work proportion (via `_calculate_weights()`)

Priority order: Continuity > 2-week urgency > EDD + proportionality + recency

#### Frontload Method (`_create_schedule_frontload`)
Concentrates work by completing projects sequentially in EDD order:

1. **EDD ordering**: Projects sorted by `end_date` (earliest first), then by `slots_remaining` (descending)
2. **Complete before moving**: Assigns all slots to current project before starting next
3. **No two-week rule**: Projects may not be touched for weeks
4. **Minimal context switching**: Optimizes for focus on one project at a time

Both methods:
- Generate renewal projects dynamically (via `_generate_renewal_projects()`)
- Iterate through time slots, skip weekends, and support fractional days
- Default to 52-week planning horizon

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

#### Projects Configuration (`projects.json`)
Projects are defined in `projects.json`:
```json
{
  "projects": [
    {
      "name": "Project Name",
      "end_date": "2024-12-31",
      "remaining_days": 15,           // Can be 0.5 for half-day
      "start_date": "2024-01-01",     // Optional: defaults to today
      "renewal_days": 5               // Optional: auto-create renewal with 5 days
    }
  ]
}
```

**Renewal Logic**:
- When `renewal_days` is set and project completes within planning horizon
- Creates in-memory renewal project: `"Project Name (Renewal)"`
- Renewal starts day after parent `end_date`, lasts 1 year
- Renewal inherits parent's color, has `parent_name` reference
- Renewals don't auto-renew (no recursive renewals)

#### Import Configuration (`import_config.json`)
Configure Excel column mapping for imports:
```json
{
  "sheet_name": 0,                    // Sheet index or name
  "header_row": 1,                    // 1-indexed row number
  "column_mapping": {
    "name": "Project Name",           // Required
    "end_date": "End Date",           // Required
    "remaining_days": "Remaining Days",  // Required
    "start_date": "Start Date",       // Optional
    "renewal_days": "Renewal Days"    // Optional
  },
  "date_format": "%Y-%m-%d"           // strptime format
}
```

**Import behavior**:
- If project exists (by name): only update `remaining_days`
- If project doesn't exist: add new project with all fields
- Returns stats: `{added, updated, unchanged}`

### Visualization System

`visualization.py` renders schedules as an enhanced calendar grid:

- **Month labels**: Shows month abbreviations (Jan, Feb, Mar) at boundaries
- **Spacing**: Tiny spaces between days, small gaps between weeks, larger margins between months
- **Tile characters**: `██` (full day same project), `█▓` (split day), `░░` (unassigned)
- **Color legend**: 6-color ANSI palette assigned round-robin to projects
  - Renewal projects shown with "(Renewal)" indicator, inherit parent color
- **Statistics**: Per-project days/week, total slots, completion dates
- **Grid rendering**: `_render_calendar_grid()` handles all spacing and month boundaries
- Uses Unicode block characters and ANSI color codes for terminal output

### Testing Structure

`tests/test_planner.py` has comprehensive coverage (55 tests):

**Core tests**:
- **TestProject**: Slot calculations, deadline logic
- **TestScheduledSlot**: Time slot properties
- **TestSchedule**: Filtering and date operations
- **TestScheduler**: Core algorithm verification
- **TestSchedulingMethods**: Edge cases for both methods

**New feature tests**:
- **TestProjectRenewal**: Renewal generation, scheduling, edge cases
- **TestEDDPrioritization**: Earliest due date ordering in both methods
- **TestDefaultWeeks**: 52-week default planning horizon
- **TestEnhancedVisualization**: Month labels, renewal indicators, calendar grid
- **TestImportFunctionality**: Config loading, project add/update, mixed operations
- **TestContinuityPriority**: Consecutive slot grouping, monopolization limits, weekend resets
- **TestEdgeCases**: Future start dates, zero renewal days, long horizons

When modifying scheduling methods:
- **Paced method**: Ensure continuity, two-week rule, and EDD tests pass
  - `test_schedule_two_week_rule`
  - `test_paced_method_distributes_work`
  - `test_edd_priority_in_paced_method`
  - `test_continuity_groups_project_work`
- **Frontload method**: Ensure concentration and EDD tests pass
  - `test_frontload_concentrates_work`
  - `test_edd_priority_in_frontload_method`

### CLI Behavior

When running `planner plan`:
1. **Both methods executed**: Always runs both paced and frontload scheduling
2. **Single tile view**: Shows tiles only for the selected method (default: paced)
3. **Dual statistics**: Displays statistics comparison for both methods
4. **Method selection**: Use `--method` or `-m` to choose which tiles to display

This allows users to compare both approaches while focusing visualization on their preferred method.

## Important Notes

- **Zero production dependencies**: Core functionality uses pure stdlib (dataclasses, argparse, json, datetime, pathlib)
- **Optional dependencies**: Excel import requires `openpyxl` (install via `uv pip install openpyxl` or extras)
- **Date handling**: Uses `datetime.date` throughout. The scheduler starts from "today" (`date.today()`) and iterates forward.
- **Project model**: Now includes optional `start_date` (defaults to today) and `renewal_days` (for auto-renewals)
- **Renewal generation**: Happens in `_generate_renewal_projects()` before scheduling, generates in-memory objects only
- **Color assignment**: Projects get colors in order from `models.py:DEFAULT_COLORS`. Wraps around if >6 projects. Renewals inherit parent color.
- **Configuration ignored**: `projects.json` and `import_config.json` are gitignored (user-specific data)
- **Default method**: Always default to paced method for backward compatibility
- **Default horizon**: 52 weeks (changed from 12 weeks) for full year planning
- **Continuity parameters**: Target 2-6 consecutive slots, max ~10 slots (1 week) to prevent monopolization
