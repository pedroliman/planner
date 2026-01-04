# Planner

A minimalist project planner with GitHub-style calendar visualizations.

## Installation

### Option 1: Install from GitHub (Recommended for Users)

```bash
uv pip install git+https://github.com/pedroliman/planner.git
```

Then create a `projects.json` file with your project data (see example below).

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
   cp projects.sample.json projects.json
   # Edit projects.json with your data
   ```

4. **Generate schedule**:
   ```bash
   source .venv/bin/activate
   quarto render schedule.qmd
   ```

   Open `schedule.html` in your browser to view the interactive schedule with calendar heatmaps and availability charts.

## Project Configuration

Create a `projects.json` file with your projects:

```json
{
  "projects": [
    {
      "name": "Project Alpha",
      "end_date": "2024-12-31",
      "remaining_days": 15,
      "start_date": "2024-01-01",
      "renewal_days": 5
    }
  ]
}
```

See `projects.sample.json` for a complete example.

## Features

- **Two scheduling methods**: Paced (balanced work distribution) and Frontload (sequential completion)
- **Interactive visualizations**: Calendar heatmaps and availability charts using Plotly
- **Project renewals**: Auto-generate renewal projects with configurable work allocation
- **52-week planning horizon**: Full year planning by default

## Testing

```bash
uv run pytest
```

## License

MIT
