# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

A minimalist project planner with interactive calendar visualizations. Projects are scheduled using two methods (paced and frontload) and visualized in a Quarto-generated HTML report.

## Workflow

1. **Configure projects**: Edit `projects.json` with project details
2. **Generate report**: Run `source .venv/bin/activate && quarto render schedule.qmd`
3. **View results**: Open `schedule.html` in browser

## Common Commands

```bash
# Setup
uv sync

# Generate schedule report
source .venv/bin/activate
quarto render schedule.qmd

# Extract pending projects from CPOS form
source .venv/bin/activate
python -m osparse.extract_cpos_projects

# Testing
uv run pytest
uv run pytest tests/test_planner.py::TestScheduler -v
uv run pytest tests/test_osparse.py -v
```

## Architecture

### Core Modules

- **models.py**: Data structures (Project, ScheduledSlot, Schedule)
- **scheduler.py**: Scheduling algorithms (paced and frontload methods)
- **analysis.py**: Visualization helpers (heatmaps, availability plots)
- **importer.py**: Excel import support (optional)

### Data Flow

```
projects.json → load_projects() → Scheduler → Schedule → Plotly visualizations → HTML report
```

### Scheduling Methods

**Paced Method** (default):
- Balances work across all projects
- Priority-first: Projects with higher priority values are scheduled first
- EDD (Earliest Due Date) prioritization (secondary to priority)
- Continuity: Groups 2-6 consecutive slots per project
- Two-week rule: Each project worked on at least once every 14 days
- Proportional allocation based on remaining work

**Frontload Method**:
- Completes projects sequentially
- Priority-first: Projects with higher priority values are scheduled first
- EDD (Earliest Due Date) prioritization (secondary to priority)
- Minimizes context switching
- No two-week rule

Both methods:
- Use 4-hour slot system (AM/PM, weekdays only)
- Support fractional days (0.5 = half-day)
- Generate renewal projects dynamically
- Default 52-week planning horizon
- Support project priorities (higher number = higher priority, default 0)

### CPOS Integration (osparse)

**osparse/extract_cpos_projects.py** extracts pending projects from NIH Current and Pending (Other) Support PDFs:
- Finds most recent `cpos*.pdf` in root directory
- Extracts projects with status = "Pending"
- Calculates `remaining_days = 226 * (first year person months) / 12`
- Updates `projects.json`:
  - Keeps all active projects (no `probability` field)
  - Updates existing pending projects (preserves `probability`)
  - Adds new pending projects with `probability: 0.5`
  - Removes pending projects not in CPOS
- Saves Excel file with parsed CPOS data

### Configuration Format

**projects.json**:
```json
{
  "projects": [
    {
      "name": "Project Name",
      "end_date": "2024-12-31",
      "remaining_days": 15,
      "start_date": "2024-01-01",    // Optional
      "renewal_days": 5,               // Optional
      "priority": 5,                   // Optional (default 0, higher = more important)
      "probability": 0.5               // Optional (0.0-1.0, for pending projects)
    }
  ]
}
```

**Priority system**:
- Priority is an integer value (higher number = higher priority)
- Default priority is 0 if not specified
- Projects with higher priority are scheduled before lower priority projects
- Priority takes precedence over EDD in both scheduling methods
- Renewal projects inherit the priority from their parent project

**Probability field** (for pending projects):
- Optional float value (0.0-1.0) indicating likelihood of project being funded
- Projects with `probability` field are considered "pending" (not yet active)
- Active projects do not have a `probability` field
- Default is 0.5 for new pending projects from CPOS extraction

**Renewal logic**:
- When `renewal_days` is set, creates renewal project after parent completes
- Renewal inherits parent's color, priority, and starts day after parent `end_date`
- Renewals don't auto-renew (no recursion)

### Visualization System

**analysis.py** provides:
- `load_projects()`: Load projects from JSON
- `create_calendar_heatmap()`: GitHub-style calendar with colored tiles
- `create_availability_plot()`: Weekly availability percentage over time
- `compute_weekly_availability()`: Calculate unscheduled time per week

Visualizations use Plotly for interactive HTML output.

### Testing

`tests/test_planner.py` has 55 tests covering:
- Core scheduling logic (TestScheduler)
- Both scheduling methods (TestSchedulingMethods)
- Project renewals (TestProjectRenewal)
- EDD prioritization (TestEDDPrioritization)
- Continuity grouping (TestContinuityPriority)
- Edge cases (TestEdgeCases)

When modifying schedulers:
- **Paced**: Ensure continuity, two-week rule, and EDD tests pass
- **Frontload**: Ensure concentration and EDD tests pass

## Important Notes

- **Main entry point**: `schedule.qmd` (Quarto document)
- **Zero core dependencies**: Stdlib only for scheduling logic
- **Optional dependencies**: plotly, pandas, openpyxl (for visualizations and imports)
- **Date handling**: Uses `datetime.date`, scheduler starts from `date.today()`
- **Time slots**: Each day = 2 slots (AM/PM), `slots_remaining = remaining_days * 2`
- **Config files**: `projects.json` and `import_config.json` are gitignored
