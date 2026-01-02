# Planner

A minimalist project planner with GitHub-style calendar visualizations.

## Quick Start

1. **Install dependencies**:
   ```bash
   uv sync
   ```

2. **Configure your projects** in `projects.json`:
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

3. **Generate schedule**:
   ```bash
   source .venv/bin/activate
   quarto render schedule.qmd
   ```

   Open `schedule.html` in your browser to view the interactive schedule with calendar heatmaps and availability charts.

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
