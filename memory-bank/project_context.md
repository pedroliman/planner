# Project Context

## Overview
A minimalist project planner that schedules research projects using two scheduling methods (paced and frontload) and generates interactive calendar visualizations via Quarto HTML reports.

## Core Purpose
Answers key research planning questions:
1. What should I focus on this week from a budget perspective?
2. Do I have too much or too little work?
3. When should I start a new project?
4. When will I get to that back-burner project?

## Architecture

### Core Components
- **models.py**: Data structures (Project, ScheduledSlot, Schedule)
- **scheduler.py**: Scheduling algorithms (paced and frontload methods)
- **analysis.py**: Visualization helpers (heatmaps, availability plots, allocation plots)
- **importer.py**: Excel import support (optional)

### Data Flow
```
projects.json → load_projects() → Scheduler → Schedule → Plotly visualizations → HTML report
```

### Scheduling Methods

**Paced Method** (default):
- Balances work across all projects proportionally
- Priority-first: Higher priority values scheduled first
- EDD (Earliest Due Date) as secondary prioritization
- Continuity: Groups 2-6 consecutive slots per project
- Two-week rule: Each project worked on at least once every 14 days
- Uses credit-based pacing model to spread work over time

**Frontload Method**:
- Completes projects sequentially
- Priority-first, then EDD prioritization
- Minimizes context switching
- No two-week rule

Both methods:
- Use 4-hour slot system (AM/PM, weekdays only)
- Support fractional days (0.5 = half-day)
- Generate renewal projects dynamically
- Default 52-week planning horizon
- Support project priorities (higher number = higher priority, default 0)

### Configuration Format

**projects.json** structure:
```json
{
  "projects": [
    {
      "name": "Project Name",
      "end_date": "2024-12-31",
      "remaining_days": 15,
      "start_date": "2024-01-01",    // Optional
      "renewal_days": 5,               // Optional
      "priority": 5                    // Optional (default 0)
    }
  ]
}
```

### Visualization System

**analysis.py** provides:
- `load_projects()`: Load projects from JSON
- `create_calendar_heatmap()`: GitHub-style calendar with colored tiles
- `create_availability_plot()`: Weekly coverage percentage over time (smoothed over 4 weeks)
- `create_project_allocation_plot()`: Stacked area chart showing % time per project (smoothed over 4 weeks, trailing average)
- `compute_weekly_availability()`: Calculate unscheduled time per week
- `compute_weekly_project_allocation()`: Calculate project allocation percentages per week

**Key visualization decisions**:
- Project allocation plot uses week-end dates for x-axis to prevent projects appearing before they start
- Projects ordered by first month (4 weeks) allocation, largest at bottom
- Month boundaries drawn at first day of each month
- Colors generated using HSL color space for visual distinction
- Tooltip shows only hovered project (hovermode="closest")
- Legend positioned vertically on right side

### Testing
55 tests covering:
- Core scheduling logic
- Both scheduling methods
- Project renewals
- EDD prioritization
- Continuity grouping
- Edge cases

## Key Technical Decisions

1. **Zero core dependencies**: Stdlib only for scheduling logic
2. **Optional dependencies**: plotly, pandas, openpyxl for visualizations
3. **Date handling**: Uses `datetime.date`, scheduler starts from `date.today()`
4. **Time slots**: Each day = 2 slots (AM/PM), but currently treating as 1 slot per day
5. **Config files**: `projects.json` and `import_config.json` are gitignored
6. **Smoothing approach**: Trailing average for project allocation (prevents future leakage), centered for coverage plot
7. **Week representation**: Plot data at week-end dates to accurately reflect when work occurs

## Entry Points
- **Main**: `schedule.qmd` (Quarto document that generates HTML report)
- **Setup**: `uv sync` to install dependencies
- **Generate report**: `source .venv/bin/activate && quarto render schedule.qmd`
- **Testing**: `uv run pytest`
