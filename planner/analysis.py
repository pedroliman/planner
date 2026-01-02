"""Analysis and visualization helpers for project schedules."""

import json
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from planner.models import Project, Schedule


def load_projects(config_path: str) -> list[Project]:
    """Load projects from JSON configuration file.

    Args:
        config_path: Path to the projects.json configuration file

    Returns:
        List of Project objects

    Raises:
        FileNotFoundError: If configuration file doesn't exist
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file '{config_path}' not found.")

    with open(path) as f:
        data = json.load(f)

    projects = []
    for i, p in enumerate(data.get("projects", [])):
        end_date = datetime.strptime(p["end_date"], "%Y-%m-%d").date()

        start_date = None
        if "start_date" in p and p["start_date"]:
            start_date = datetime.strptime(p["start_date"], "%Y-%m-%d").date()

        renewal_days = None
        if "renewal_days" in p and p["renewal_days"]:
            renewal_days = float(p["renewal_days"])

        project = Project(
            name=p["name"],
            end_date=end_date,
            remaining_days=float(p["remaining_days"]),
            start_date=start_date,
            renewal_days=renewal_days,
            _color_index=i,
        )
        projects.append(project)

    return projects


def compute_weekly_availability(schedule: Schedule, num_weeks: int) -> list[dict]:
    """Compute availability percentage for each week in the schedule.

    Args:
        schedule: Schedule object to analyze
        num_weeks: Number of weeks to analyze

    Returns:
        List of dictionaries with weekly availability statistics
    """
    if not schedule.start_date:
        return []

    weekly_stats = []
    current_week_start = schedule.start_date

    for week_num in range(num_weeks):
        # Count slots in this week
        total_slots = 0
        unscheduled_slots = 0

        # Iterate through each day in the week
        for day_offset in range(7):
            current_date = current_week_start + timedelta(days=day_offset)

            # Skip weekends (Saturday=5, Sunday=6)
            if current_date.weekday() >= 5:
                continue

            # Count slots for this day
            day_slots = schedule.get_slots_for_date(current_date)

            if not day_slots:
                # If no slots exist for this date, assume 1 unscheduled slot
                total_slots += 1
                unscheduled_slots += 1
            else:
                # We always have 1 slot per weekday
                total_slots += 1

                # Check if the slot is scheduled
                is_scheduled = any(s.project is not None for s in day_slots)

                # Count unscheduled slots
                if not is_scheduled:
                    unscheduled_slots += 1

        percent_available = (unscheduled_slots / total_slots * 100) if total_slots > 0 else 100.0

        weekly_stats.append({
            'week_number': week_num,
            'start_date': current_week_start,
            'total_slots': total_slots,
            'unscheduled_slots': unscheduled_slots,
            'percent_available': percent_available
        })

        # Move to next week
        current_week_start += timedelta(weeks=1)

    return weekly_stats


def create_calendar_heatmap(schedule: Schedule, title: str) -> Optional[go.Figure]:
    """Create a calendar heatmap showing categorical project data.

    Args:
        schedule: Schedule object to visualize
        title: Title for the plot

    Returns:
        Plotly Figure object or None if no data
    """
    # Build a mapping of dates to projects
    date_to_project = {}
    all_projects = set()

    for slot in schedule.slots:
        if slot.project:
            date_to_project[slot.date] = slot.project.name
            all_projects.add(slot.project.name)

    # Get unique project names and assign them numeric values
    project_names = sorted(list(all_projects))
    project_to_num = {name: i for i, name in enumerate(project_names)}

    # Color mapping using a generated color palette based on number of projects
    num_projects = max(len(project_names), 1)
    color_scale = px.colors.qualitative.Alphabet if num_projects <= len(px.colors.qualitative.Alphabet) else px.colors.qualitative.Light24
    if num_projects > len(color_scale):
        # Fallback to a continuous colorscale and sample distinct colors
        base_scale = px.colors.sequential.Viridis
        color_scale = [base_scale[int(i * (len(base_scale) - 1) / (num_projects - 1))] for i in range(num_projects)]
    colors = color_scale[:num_projects]

    # Build data for plotly
    dates = sorted(schedule.get_unique_dates())
    if not dates:
        return None

    # Create a dataframe with all dates in the range
    start_date = dates[0]
    end_date = dates[-1]

    all_dates = pd.date_range(start=start_date, end=end_date, freq='D')

    # Prepare data for heatmap
    df_data = []
    for d in all_dates:
        date_obj = d.date()
        # Skip weekends
        if date_obj.weekday() >= 5:
            continue

        project_name = date_to_project.get(date_obj, None)

        df_data.append({
            'date': date_obj,
            'week': date_obj.isocalendar()[1],
            'weekday': date_obj.weekday(),
            'project': project_name,
            'value': project_to_num.get(project_name, -1) if project_name else -1
        })

    df = pd.DataFrame(df_data)

    # Create the heatmap using plotly
    # We'll use a scatter plot to create a calendar-like view

    # Group by week and weekday
    df['week_start'] = df['date'].apply(lambda x: x - timedelta(days=x.weekday()))
    week_starts = sorted(df['week_start'].unique())
    week_to_x = {w: i for i, w in enumerate(week_starts)}
    df['x'] = df['week_start'].map(week_to_x)
    df['y'] = 4 - df['weekday']  # Reverse Y axis (Monday at top)

    # Create hover text
    df['hover_text'] = df.apply(
        lambda row: f"{row['date'].strftime('%A, %B %d, %Y')}<br>{row['project'] if row['project'] else 'Unscheduled'}",
        axis=1
    )

    # Create figure
    fig = go.Figure()

    # Add unscheduled days
    df_unscheduled = df[df['project'].isna()]
    if not df_unscheduled.empty:
        fig.add_trace(go.Scatter(
            x=df_unscheduled['x'],
            y=df_unscheduled['y'],
            mode='markers',
            marker=dict(
                size=15,
                color='#1e293b',
                symbol='square',
                line=dict(color='#334155', width=1)
            ),
            text=df_unscheduled['hover_text'],
            hovertemplate='%{text}<extra></extra>',
            name='Unscheduled',
            showlegend=True
        ))

    # Add each project as a separate trace
    for i, project_name in enumerate(project_names):
        df_proj = df[df['project'] == project_name]
        if not df_proj.empty:
            fig.add_trace(go.Scatter(
                x=df_proj['x'],
                y=df_proj['y'],
                mode='markers',
                marker=dict(
                    size=15,
                    color=colors[i % len(colors)],
                    symbol='square',
                ),
                text=df_proj['hover_text'],
                hovertemplate='%{text}<extra></extra>',
                name=project_name,
                showlegend=True
            ))

    # Create month labels for x-axis
    # Find the start of each month in the date range
    month_positions = {}
    current_month = None
    for idx, week_start in enumerate(week_starts):
        month_key = (week_start.year, week_start.month)
        if month_key != current_month:
            current_month = month_key
            month_positions[idx] = week_start.strftime('%b %Y')

    # Update layout with month labels
    fig.update_layout(
        title=title,
        xaxis=dict(
            title="",
            showgrid=False,
            zeroline=False,
            tickmode='array',
            tickvals=list(month_positions.keys()),
            ticktext=list(month_positions.values()),
            tickangle=0
        ),
        yaxis=dict(
            title="",
            showgrid=False,
            zeroline=False,
            tickmode='array',
            tickvals=[0, 1, 2, 3, 4],
            ticktext=['Fri', 'Thu', 'Wed', 'Tue', 'Mon']
        ),
        height=300,
        hovermode='closest',
        plot_bgcolor='#0f172a',
        paper_bgcolor='#0f172a',
        font=dict(color='#e2e8f0')
    )

    return fig


def create_availability_plot(
    paced_availability: list[dict],
    frontload_availability: list[dict]
) -> go.Figure:
    """Create weekly availability comparison plot.

    Args:
        paced_availability: Weekly availability stats for paced method
        frontload_availability: Weekly availability stats for frontload method

    Returns:
        Plotly Figure object
    """
    fig = go.Figure()

    # Paced method
    paced_dates = [w['start_date'] for w in paced_availability]
    paced_percents = [w['percent_available'] for w in paced_availability]

    fig.add_trace(go.Scatter(
        x=paced_dates,
        y=paced_percents,
        mode='lines+markers',
        name='Paced Method',
        line=dict(color='#60a5fa', width=2),
        marker=dict(size=6),
        hovertemplate='%{x|%b %d, %Y}<br>Available: %{y:.1f}%<extra></extra>'
    ))

    # Frontload method
    frontload_dates = [w['start_date'] for w in frontload_availability]
    frontload_percents = [w['percent_available'] for w in frontload_availability]

    fig.add_trace(go.Scatter(
        x=frontload_dates,
        y=frontload_percents,
        mode='lines+markers',
        name='Frontload Method',
        line=dict(color='#fbbf24', width=2),
        marker=dict(size=6),
        hovertemplate='%{x|%b %d, %Y}<br>Available: %{y:.1f}%<extra></extra>'
    ))

    # Create month boundaries for vertical lines
    month_boundaries = []
    current_month = None
    for w in paced_availability:
        date_obj = w['start_date']
        month_key = (date_obj.year, date_obj.month)
        if month_key != current_month:
            current_month = month_key
            month_boundaries.append(date_obj)

    # Add vertical lines at month boundaries
    for boundary in month_boundaries:
        fig.add_vline(
            x=boundary,
            line_width=1,
            line_dash="dash",
            line_color="#334155",
            opacity=0.5
        )

    fig.update_layout(
        title="Weekly Availability Percentage",
        xaxis_title="",
        yaxis_title="Availability (%)",
        hovermode='x unified',
        height=500,
        plot_bgcolor='#0f172a',
        paper_bgcolor='#0f172a',
        font=dict(color='#e2e8f0'),
        yaxis=dict(range=[0, 100]),
        xaxis=dict(
            tickformat='%b\n%Y',
            dtick='M1',  # Monthly ticks
            ticklabelmode='period'
        )
    )

    return fig
