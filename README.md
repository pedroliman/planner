# Planner

A minimalist project planner with GitHub-style calendar visualizations.

## Installation

### Option 1: Install from GitHub (Recommended for Users)

```bash
uv pip install git+https://github.com/pedroliman/planner.git
```

Then create a `workers/<your-name>.json` file with your project data (see example below).

### Option 2: Clone and Develop Locally

1. **Clone the repository**:
   ```bash
   git clone https://github.com/pedroliman/planner.git
   cd planner
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

3. **Configure your projects**:
   ```bash
   mkdir -p workers
   # Edit workers/pedro.json (or workers/<your-name>.json) with your data
   ```

4. **Run the app**:
   ```bash
   source .venv/bin/activate
   shiny run --reload app.py
   ```

   Use the **Worker** selector in the sidebar to switch between workers' project files.

5. **Or generate the static report**:
   ```bash
   quarto render schedule.qmd                    # default worker (pedro)
   PLANNER_WORKER=alice quarto render schedule.qmd
   ```

   Open `schedule.html` in your browser to view the interactive schedule with calendar heatmaps and availability charts.

## Workers

Each worker has their own projects file, named after them, under `workers/`:

```
workers/pedro.json    # default worker
workers/alice.json
```

Adding a file there is all it takes for a worker to show up in the app's selector
(worker names are lowercase and may contain letters, digits, `-` and `_`).
`workers/` is gitignored since it holds personal data.

If you want your project files synced and backed up, make `workers/` a symlink to
a folder in your cloud storage instead of a real directory:

```bash
ln -s "$HOME/path/to/cloud/planner-worker-days" workers
```

Everything resolves through the link normally. Note that `.gitignore` lists both
`workers/` and `workers` so the symlink itself stays ignored.

## Project Configuration

Create a `workers/<worker>.json` file with your projects:

```json
{
  "projects": [
    {
      "name": "Project Alpha",
      "remaining_days": 15,
      "end_date": "2024-12-31",
      "start_date": "2024-01-01",
      "years_left": 3,
      "renewal_days": 5
    }
  ]
}
```

Only `name` and `remaining_days` are required. Omit `end_date` and the project is
assumed to run for one year from its `start_date` (or from today if no start date
is given), matching the usual annual budget cycle.

`years_left` is how many years of funding are left *including* the current one, so
the default of 1 means no renewal, 2 means one renewal year, 5 means four. Each
renewal year is one year long and starts where the previous one ended, so a long
horizon shows the whole multi-year commitment.

Renewal years shrink as your salary grows: a grant year is a fixed pot of money,
so each year buys `1 / (1 + growth)` of the previous year's days. The rate is a
model setting (`Annual salary growth (%)` in the sidebar, 4% by default), so
`renewal_days` is optional -- give it only to pin the *first* renewal year's
budget, and later years are discounted from there.

Projects with a `probability` field are treated as pending; those without are active.

## Features

- **Two scheduling methods**: Paced (balanced work distribution) and Frontload (sequential completion)
- **Interactive visualizations**: Calendar heatmaps and availability charts using Plotly
- **Multi-year renewals**: Auto-generate one renewal year per `years_left`, each
  discounted for salary growth
- **52-week planning horizon**: Full year by default, up to 10 years in the app

## Testing

```bash
uv run pytest
```

## License

MIT
