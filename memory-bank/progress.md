# Progress Tracking

## Recent Changes

### 2026-02-26

#### Added Project Allocation Visualization (13:45)
- **Task**: Implement stacked area plot showing % allocation per project below weekly coverage plot
- **Changes**:
  - Added `compute_weekly_project_allocation()` function in analysis.py
  - Added `create_project_allocation_plot()` function in analysis.py
  - Updated schedule.qmd to import and display new visualization
  - Applied 4-week trailing smoothing to project allocation data
  - Used same HSL color scheme as calendar heatmap for consistency
- **Files modified**: `planner/analysis.py`, `schedule.qmd`

#### Fixed Project Ordering and Legend Position (14:00)
- **Task**: Order projects by allocation size, fix tooltip, move legend
- **Changes**:
  - Projects now ordered by first month (4 weeks) allocation, largest at bottom
  - Changed hovermode from "x unified" to "closest" for cleaner tooltips
  - Moved legend from horizontal bottom to vertical right side
  - Increased right margin to accommodate legend
- **Files modified**: `planner/analysis.py`

#### Fixed Project Start Date Visualization (14:15)
- **Task**: Prevent IMABC from appearing before July 1st start date
- **Changes**:
  - Changed from week-start to week-end dates for x-axis plotting
  - Prevents projects from appearing before they actually start
  - Updated month boundary lines to draw at actual first day of each month
  - Applied trailing 4-week average instead of centered to prevent future data leakage
- **Files modified**: `planner/analysis.py`

#### Applied 4-Week Smoothing (14:30)
- **Task**: Update smoothing window from 3 to 4 weeks for both plots
- **Changes**:
  - Project allocation plot: 4-week trailing average
  - Coverage plot: 4-week centered average
  - Updated figure caption
- **Files modified**: `planner/analysis.py`, `schedule.qmd`

#### Removed and Restored Smoothing (14:35-14:40)
- **Task**: Remove smoothing entirely, then restore it
- **Changes**:
  - Briefly removed all smoothing to show raw data
  - User requested to undo, restored 4-week smoothing
  - Final state: 4-week smoothing in place for both plots
- **Files modified**: `planner/analysis.py`, `schedule.qmd`

#### Implemented Memory Bank System (14:45)
- **Task**: Create Claude-style memory bank with project_context and progress files
- **Changes**:
  - Created `.claude/` directory
  - Added `project_context.md` with architecture, decisions, and key patterns
  - Added `progress.md` with timestamped task tracking
- **Files created**: `.claude/project_context.md`, `.claude/progress.md`

## Active Patterns

### When modifying visualizations:
- Always test by running `quarto render schedule.qmd`
- Check that date alignments are accurate (week-end vs week-start matters)
- Consider smoothing implications (trailing vs centered)
- Verify month boundaries align correctly

### When working with schedules:
- Paced method should respect two-week rule and continuity
- Projects with same priority use EDD as tiebreaker
- Renewal projects inherit parent priority and color

## Known Issues
None currently.

## Next Steps
None identified.
