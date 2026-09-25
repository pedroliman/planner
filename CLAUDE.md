# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

A minimalist project planner with interactive calendar visualizations. Projects are scheduled using two methods (paced and frontload) and visualized in a Quarto-generated HTML report.

## Workflow

1. **Configure projects**: Edit `workers/<worker>.json` (e.g. `workers/pedro.json`) with project details
2. **Run the app**: `source .venv/bin/activate && shiny run --reload app.py`, then pick the worker in the sidebar
3. **Or generate the report**: `quarto render schedule.qmd` and open `schedule.html`

## Common Commands

```bash
# Setup
uv sync

# Run the interactive app (worker selector in sidebar)
source .venv/bin/activate
shiny run --reload app.py

# Generate schedule report (default worker, or override)
source .venv/bin/activate
quarto render schedule.qmd
PLANNER_WORKER=alice quarto render schedule.qmd

# Extract pending projects from CPOS form for a worker
source .venv/bin/activate
python -m osparse.extract_cpos_projects --worker pedro

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
- **workers.py**: Per-worker config resolution (`worker_config_path`, `list_workers`)
- **importer.py**: Excel import support (optional)

### Data Flow

```
workers/<worker>.json → load_projects() → Scheduler → Schedule → Plotly visualizations → app/HTML report
```

### Workers

Each worker keeps their own projects file, named after them, in `workers/`:

```
workers/pedro.json    # DEFAULT_WORKER
workers/alice.json
```

- `planner/workers.py` is the single source of truth for resolving files:
  `worker_config_path(worker)` → `workers/<worker>.json`, `list_workers()` →
  discovered names with the default first, `normalize_worker()` validates names
  (lowercase, `[a-z0-9_-]`, rejects path separators).
- **app.py**: sidebar `Worker` selector. Switching a worker reloads its file,
  repopulates the active/pending checkbox groups (all active selected, no
  pending), and notifies. A missing or malformed file shows an error
  notification instead of crashing the app.
- **schedule.qmd**: renders `DEFAULT_WORKER`; override with the
  `PLANNER_WORKER` env var.
- **osparse**: `python -m osparse.extract_cpos_projects --worker <name>` writes
  to that worker's file and prefers a CPOS PDF whose name mentions the worker
  (e.g. `cpos-pedro.pdf`), falling back to any `cpos*.pdf`.
- Backwards compatibility: a legacy root `projects.json` is used for the default
  worker when `workers/pedro.json` does not exist.
- `workers/` is gitignored (user-specific data).

**On this machine `workers/` is a symlink, not a real directory:**

```
workers -> ~/Library/CloudStorage/OneDrive-RANDCorporation/03-Projects/planner-worker-days
```

- Worker JSON lives in OneDrive so it is synced and backed up without ever being
  committed. Everything resolves through the link normally -- no code knows or
  cares that `workers/` is a symlink.
- `.gitignore` needs **both** `workers/` and a bare `workers`: the trailing-slash
  pattern only matches real directories, so without the bare entry the symlink
  itself shows up as untracked.
- The symlink is not tracked, so a fresh clone elsewhere will not have it.
  Recreate it with:
  `ln -s "$HOME/Library/CloudStorage/OneDrive-RANDCorporation/03-Projects/planner-worker-days" workers`
- Anything written into `workers/` syncs to OneDrive, including the Excel file
  osparse saves alongside the JSON.

### Scheduling Methods

**Paced Method** (default):
- Balances work across all projects
- Token bucket: each project accrues credit at its own rate (remaining days /
  workdays left in its window) and only claims a slot when it is behind pace
- Priority-first: Projects with higher priority values are scheduled first
- EDD (Earliest Due Date) prioritization (secondary to priority)
- Continuity: Groups 2-6 consecutive slots per project
- Two-week rule: Each project worked on at least once every 14 days
- Proportional allocation based on remaining work

Priority in the paced method:
- Priority leads every selection ordering (behind-pace picks, the must-do rule,
  and the cumulative feasibility guard). It must stay ahead of pacing credit and
  slack, which are continuous/near-continuous, or it never gets consulted
- Priority is **ordinal**: only the ranking matters, so 5 and 100 behave the same
  against a field of 0s
- Priority does not let a project hog capacity -- credit accrues at its own paced
  rate, so it claims a slot only when behind its own pace
- Deadline feasibility can still preempt priority: the must-do guard fires before
  priority-based selection, so a project that needs every one of its remaining
  workdays takes the slot even from a higher-priority project that has slack.
  Raising priority therefore reduces a project's reassigned days but may not zero
  them out

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

### Day Reassignment (paced only)

`create_schedule(reassign_days=True, reassignment_cadence_days=30)` tracks days
that have to move off this worker's plate:

- Every `reassignment_cadence_days` calendar days (default 30), each project's
  leftover pacing credit is the work it was owed but lost to contention. Whole
  days are booked as reassigned, then removed from the remaining budget so the
  rest of the horizon is planned without them. Fractional credit keeps accruing,
  so a project a fraction of a day behind is not charged a whole day.
- A project reaching its `end_date` hands off whatever budget is left, and any
  quota still unbooked is closed out on the last day of the horizon -- otherwise a
  project whose deadline sits past the horizon could never shed anything.
- Bookings land on `Schedule.reassignments` (`ReassignedDays`: project, checkpoint
  date, days) with `Schedule.reassigned_days_for()` and
  `Schedule.total_reassigned_days` helpers.
- Off by default; requesting it with `method="frontload"` raises `ValueError`.
- Who receives the days (and their relative cost) is not modelled yet -- only the
  days leaving this worker are tracked.

**How much a project owes** -- `_due_by_horizon()` is the measuring stick, not
`slots_remaining`:

- Deadline inside the horizon: the whole remaining budget.
- Deadline past the horizon: the paced share (floored) of the project's window
  that falls inside the horizon. A project with a 2028 deadline still owes days
  inside a 2026 horizon, so it can and does shed.
- Deadline before `start_date`, or window starting after the horizon ends: 0
  (stale projects never shed; they still warn).

**The solve loop** -- `_solve_paced_with_reassignment` schedules, measures the
shortfall, and re-schedules with per-project quotas:

- The shortfall is `_due_by_horizon - scheduled - already reassigned`. Quotas grow
  for the *lowest-priority* tier that still has a shortfall, so high-priority work
  is the last to be handed off.
- `_trim_unneeded_quota` takes back quota once freeing a project's days lets it
  book more than it owed -- without it the same day gets counted twice, as
  scheduled and as reassigned.
- Every pass is scored `(total shortfall, total reassigned)` and the best is
  returned, so a trim that goes too far is simply not the pass that wins.
- A project whose shortfall fails to shrink for `STUCK_PATIENCE` (2) consecutive
  passes is capacity-bound: its quota stops growing and the solver warns that days
  are "behind pace" rather than inflating quotas to the iteration cap.
- `DEFAULT_MAX_REASSIGNMENT_ITERATIONS` is 24 -- the loop needs room past the first
  feasible pass because it also trims back.

`schedule.end_date` is the **inclusive** last day covered
(`start + num_weeks * 7 - 1`, see `_horizon_end`). Reassignment books close-outs on
real iterated days, so an off-by-one here makes deadlines on the boundary
unbookable and the solver runs to its cap.

Known residual: a paced project can leave workdays idle inside its own window
after shedding, because its accrual rate is fixed from the initial budget while
shedding shrinks that budget. It is the paced allocator refusing to work ahead of
pace, not double-shedding: `scheduled + reassigned` still stays within budget.

In the app: the sidebar `Reassignment` section (checkbox, off by default, plus a
cadence input) feeds the paced schedule, and the `Reassignment` tab shows a
projects x months table of reassigned days. Selecting more pending projects
oversubscribes capacity and increases the reassigned totals.

### CPOS Integration (osparse)

**osparse/extract_cpos_projects.py** extracts pending projects from NIH Current and Pending (Other) Support PDFs:
- Finds most recent `cpos*.pdf` in root directory (worker-tagged names preferred)
- Extracts projects with status = "Pending"
- Calculates `remaining_days = 226 * (first year person months) / 12`
- Updates the worker's file (`--worker`, default `pedro`):
  - Keeps all active projects (no `probability` field)
  - Updates existing pending projects (rebuilt from the CPOS row, but
    `probability` and every field in `HAND_MAINTAINED_FIELDS` -- `priority`,
    `years_left`, `renewal_days`, `renewal_lag_days` -- are carried over, since
    the PDF knows nothing about them)
  - Adds new pending projects with `probability: 0.5`
  - Removes pending projects not in CPOS
- Saves Excel file with parsed CPOS data

### Configuration Format

**workers/&lt;worker&gt;.json**:
```json
{
  "projects": [
    {
      "name": "Project Name",
      "remaining_days": 15,
      "end_date": "2024-12-31",      // Optional (default: start_date + 1 year)
      "start_date": "2024-01-01",    // Optional
      "renewal_days": 5,               // Optional (first renewal year only)
      "years_left": 3,                 // Optional (default 1 = no renewal)
      "priority": 5,                   // Optional (default 0, higher = more important)
      "probability": 0.5               // Optional (0.0-1.0, for pending projects)
    }
  ]
}
```

Only `name` and `remaining_days` are required.

**Default end date**:
- A missing or `null` `end_date` defaults to `DEFAULT_DURATION_DAYS` (365) after
  `start_date`, or after today when no `start_date` is given -- the annual budget
  cycle most projects follow
- `DEFAULT_DURATION_DAYS` lives in `models.py` and is the same span used for
  generated renewal projects

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

**Renewal logic** (`Scheduler._generate_renewal_projects`):
- `years_left` counts the **current** year, so it is one more than the number of
  renewals: 1 (default) = none, 2 = one renewal, 5 = four. `Project.renewal_years`
  is the single source of that arithmetic
- Renewal years chain: year *n* starts the day after year *n-1* ends (plus
  `renewal_lag_days`, applied at **every** boundary) and runs
  `DEFAULT_DURATION_DAYS` from that previous end date -- a lag shortens the window
  rather than shifting it
- Names: first renewal keeps the legacy `"<name> (Renewal)"`, later ones are
  `"<name> (Renewal 2)"`, ... Build them with `models.renewal_name()`, never by
  string concatenation -- `app._stable_color_map` relies on it to keep a project's
  color across all of its years
- Renewal inherits parent's color and priority; renewals don't auto-renew
  (`renewal_years == 0` when `is_renewal`)
- Years whose window starts past the horizon are not created, so a short horizon
  costs nothing and a long one reveals the full multi-year load (that is the point
  of `years_left`: extend the horizon, read "Total days" in the summary card)
- Backwards compatibility: a config with `renewal_days` but no `years_left` still
  produces exactly one renewal

**Salary growth** (`Scheduler.renewal_days_for_year`):
- A grant year is a fixed pot of money, so a raise buys fewer days: each renewal
  year is the previous one divided by `1 + annual_salary_growth`
  (`DEFAULT_ANNUAL_SALARY_GROWTH` = 0.04 in `models.py`)
- `Scheduler(..., annual_salary_growth=...)` is the model setting; the app exposes
  it as `Annual salary growth (%)` in the sidebar. Values <= -1 raise `ValueError`
- With `renewal_days`: that value **is** year 1 of the renewals, discounting starts
  at year 2. Without it: `remaining_days` is the baseline, so the first renewal is
  already one year of growth cheaper
- Caveat: `remaining_days` is what is *left* this year, not the annual allocation.
  A project observed mid-year therefore derives renewal years that are too small --
  set `renewal_days` explicitly for those

### Visualization System

**analysis.py** provides:
- `load_projects()`: Load projects from JSON
- `create_calendar_heatmap()`: GitHub-style calendar with colored tiles
- `create_availability_plot()`: Weekly availability percentage over time
- `compute_weekly_availability()`: Calculate unscheduled time per week
- `compute_monthly_reassigned_days()`: Long-format reassigned days per project/month
- `create_reassignment_table()`: Projects x months table of reassigned days (plus totals)

Visualizations use Plotly for interactive HTML output.

### Testing

`tests/test_planner.py` covers:
- Core scheduling logic (TestScheduler)
- Both scheduling methods (TestSchedulingMethods)
- Project renewals (TestProjectRenewal)
- Multi-year renewals and salary discounting (TestYearsLeft)
- EDD prioritization (TestEDDPrioritization)
- Continuity grouping (TestContinuityPriority)
- Edge cases (TestEdgeCases)
- Reassignment: horizon boundary, `_due_by_horizon`, solver behaviour, a swept
  list of workloads checked against the reassignment invariants, and the real
  `workers/pedro.json` shape (TestReassignment*)

When modifying schedulers:
- **Paced**: Ensure continuity, two-week rule, and EDD tests pass
- **Frontload**: Ensure concentration and EDD tests pass
- **Reassignment**: `TestReassignmentInvariants` sweeps `SCENARIOS` -- add a
  workload there rather than writing a one-off test. The invariants that actually
  catch regressions are "never sheds more than the budget", "does not overshoot
  what was due", and "does not idle capacity it could have used"

## Important Notes

- **Main entry point**: `app.py` (Shiny app); `schedule.qmd` (Quarto document) is the static alternative
- **Zero core dependencies**: Stdlib only for scheduling logic
- **Optional dependencies**: plotly, pandas, openpyxl (for visualizations and imports)
- **Date handling**: Uses `datetime.date`, scheduler starts from `date.today()`
- **Time slots**: Each day = 2 slots (AM/PM), `slots_remaining = remaining_days * 2`
- **Config files**: `workers/` (and legacy `projects.json`) plus `import_config.json` are gitignored
