"""Analysis and visualization helpers for project schedules."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from planner.models import Project, Schedule


def _hsl_to_rgb(hue: float, saturation: float, lightness: float) -> tuple[int, int, int]:
    """Convert HSL color to RGB.

    Args:
        hue: Hue in degrees (0-360)
        saturation: Saturation as percentage (0-100)
        lightness: Lightness as percentage (0-100)

    Returns:
        Tuple of (R, G, B) integers (0-255)
    """
    h = hue / 60.0
    s = saturation / 100.0
    l = lightness / 100.0

    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs(h % 2 - 1))
    m = l - c / 2

    if h < 1:
        r, g, b = c, x, 0
    elif h < 2:
        r, g, b = x, c, 0
    elif h < 3:
        r, g, b = 0, c, x
    elif h < 4:
        r, g, b = 0, x, c
    elif h < 5:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x

    return (
        int((r + m) * 255),
        int((g + m) * 255),
        int((b + m) * 255),
    )


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

        # Only set start_date if explicitly provided in JSON
        # If None, scheduler will use its own start_date
        start_date = None
        if "start_date" in p and p["start_date"]:
            start_date = datetime.strptime(p["start_date"], "%Y-%m-%d").date()

        renewal_days = None
        if "renewal_days" in p and p["renewal_days"]:
            renewal_days = float(p["renewal_days"])

        renewal_lag_days = None
        if "renewal_lag_days" in p and p["renewal_lag_days"] is not None:
            renewal_lag_days = int(p["renewal_lag_days"])

        priority = 0
        if "priority" in p and p["priority"] is not None:
            priority = int(p["priority"])

        probability = 1.0
        if "probability" in p and p["probability"] is not None:
            probability = float(p["probability"])

        project = Project(
            name=p["name"],
            end_date=end_date,
            remaining_days=float(p["remaining_days"]),
            start_date=start_date,
            renewal_days=renewal_days,
            renewal_lag_days=renewal_lag_days,
            priority=priority,
            probability=probability,
            _color_index=i,
        )
        projects.append(project)

    return projects


def filter_projects_by_probability(
    projects: list[Project], min_probability: float
) -> list[Project]:
    """Filter projects by minimum probability threshold.

    Args:
        projects: List of Project objects to filter
        min_probability: Minimum probability threshold (0-1)

    Returns:
        Filtered list of Project objects with probability >= min_probability
    """
    return [p for p in projects if p.probability >= min_probability]


def compute_monthly_unassigned_days(
    schedule: Schedule, include_zero_months: bool = False
) -> pd.DataFrame:
    """Compute the number of unassigned days per month.

    Args:
        schedule: Schedule object to analyze
        include_zero_months: Include months with 0 unassigned days

    Returns:
        DataFrame with columns: year, month, month_name, unassigned_days
        By default, only includes months with at least one unassigned day
    """
    if not schedule.slots:
        return pd.DataFrame(columns=["year", "month", "month_name", "unassigned_days"])

    # Count unassigned days per month
    monthly_counts = {}

    for slot in schedule.slots:
        # Only count weekdays (weekends are already excluded from slots)
        if slot.project is None:
            month_key = (slot.date.year, slot.date.month)
            if month_key not in monthly_counts:
                monthly_counts[month_key] = 0
            monthly_counts[month_key] += 1

    # Convert to DataFrame
    data = []
    for (year, month), count in sorted(monthly_counts.items()):
        # Only include months with at least one unassigned day
        if count > 0:
            month_name = datetime(year, month, 1).strftime("%B %Y")
            data.append(
                {
                    "year": year,
                    "month": month,
                    "month_name": month_name,
                    "unassigned_days": count,
                }
            )

    df = pd.DataFrame(data)
    if not include_zero_months:
        return df

    # Include all months in the schedule range, filling missing with 0.
    start = schedule.start_date or min(s.date for s in schedule.slots)
    end = schedule.end_date or max(s.date for s in schedule.slots)
    month_starts = pd.date_range(
        start=date(start.year, start.month, 1),
        end=date(end.year, end.month, 1),
        freq="MS",
    )
    all_months = pd.DataFrame(
        {
            "year": month_starts.year,
            "month": month_starts.month,
        }
    )
    all_months["month_name"] = month_starts.strftime("%B %Y")

    if df.empty:
        all_months["unassigned_days"] = 0
        return all_months

    merged = all_months.merge(df, on=["year", "month"], how="left", suffixes=("", "_y"))
    merged["unassigned_days"] = merged["unassigned_days"].fillna(0).astype(int)
    merged = merged[["year", "month", "month_name", "unassigned_days"]]
    return merged


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

        percent_available = (
            (unscheduled_slots / total_slots * 100) if total_slots > 0 else 100.0
        )

        weekly_stats.append(
            {
                "week_number": week_num,
                "start_date": current_week_start,
                "total_slots": total_slots,
                "unscheduled_slots": unscheduled_slots,
                "percent_available": percent_available,
            }
        )

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
    # Build a mapping of dates to projects and collect project end_dates
    date_to_project = {}
    project_info = {}  # project_name -> Project object

    for slot in schedule.slots:
        if slot.project:
            date_to_project[slot.date] = slot.project.name
            if slot.project.name not in project_info:
                project_info[slot.project.name] = slot.project

    # Sort projects by end_date, then by name for stability
    sorted_projects = sorted(
        project_info.items(),
        key=lambda x: (x[1].end_date, x[0])
    )
    project_names = [name for name, _ in sorted_projects]
    project_to_num = {name: i for i, name in enumerate(project_names)}

    # Generate divergent colors by spreading projects around the color wheel
    # This ensures nearby end_dates get visually different colors
    num_projects = len(project_names)
    colors = []
    for i in range(num_projects):
        # Use HSL color space, spread hue across 0-360 degrees
        hue = (i * 360 / max(num_projects, 1)) % 360
        # Use 65% saturation and 45% lightness for vibrant but readable colors
        # Convert HSL to hex (using standard HSL to RGB conversion)
        rgb = _hsl_to_rgb(hue, 65, 45)
        hex_color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        colors.append(hex_color)

    # Build data for plotly
    dates = sorted(schedule.get_unique_dates())
    if not dates:
        return None

    # Create a dataframe with all dates in the range
    start_date = dates[0]
    end_date = dates[-1]

    all_dates = pd.date_range(start=start_date, end=end_date, freq="D")

    # Prepare data for heatmap
    df_data = []
    for d in all_dates:
        date_obj = d.date()
        # Skip weekends
        if date_obj.weekday() >= 5:
            continue

        project_name = date_to_project.get(date_obj, None)

        df_data.append(
            {
                "date": date_obj,
                "week": date_obj.isocalendar()[1],
                "weekday": date_obj.weekday(),
                "project": project_name,
                "value": project_to_num.get(project_name, -1) if project_name else -1,
            }
        )

    df = pd.DataFrame(df_data)

    # Create the heatmap using plotly
    # We'll use a scatter plot to create a calendar-like view

    # Group by week and weekday
    df["week_start"] = df["date"].apply(lambda x: x - timedelta(days=x.weekday()))
    week_starts = sorted(df["week_start"].unique())
    week_to_x = {w: i for i, w in enumerate(week_starts)}
    df["x"] = df["week_start"].map(week_to_x)
    df["y"] = 4 - df["weekday"]  # Reverse Y axis (Monday at top)

    # Create hover text
    df["hover_text"] = df.apply(
        lambda row: f"{row['date'].strftime('%A, %B %d, %Y')}<br>{row['project'] if row['project'] else 'Unscheduled'}",
        axis=1,
    )

    # Create figure
    fig = go.Figure()

    # Calculate dimensions for square cells
    # Each cell should be a square, so we need to calculate width and height properly
    num_weeks = len(week_starts)
    cell_size = 24  # pixels per cell (increased from 16)
    gap_between_cells = 2  # spacing (reduced from 4)

    # Add unscheduled days
    df_unscheduled = df[df["project"].isna()]
    if not df_unscheduled.empty:
        fig.add_trace(
            go.Scatter(
                x=df_unscheduled["x"],
                y=df_unscheduled["y"],
                mode="markers",
                marker=dict(
                    size=cell_size,
                    color="#e5e7eb",  # Light gray for unscheduled
                    symbol="square",
                    line=dict(color="#d1d5db", width=1),
                ),
                text=df_unscheduled["hover_text"],
                hovertemplate="%{text}<extra></extra>",
                name="Unscheduled",
                showlegend=True,
            )
        )

    # Add each project as a separate trace
    for i, project_name in enumerate(project_names):
        df_proj = df[df["project"] == project_name]
        if not df_proj.empty:
            fig.add_trace(
                go.Scatter(
                    x=df_proj["x"],
                    y=df_proj["y"],
                    mode="markers",
                    marker=dict(
                        size=cell_size,
                        color=colors[i % len(colors)],
                        symbol="square",
                        line=dict(
                            color="white", width=2
                        ),  # White border for separation
                    ),
                    text=df_proj["hover_text"],
                    hovertemplate="%{text}<extra></extra>",
                    name=project_name,
                    showlegend=True,
                )
            )

    # Create month labels for x-axis
    # Find the start of each month in the date range
    month_positions = {}
    current_month = None
    last_label_idx = -999  # Track last label position to avoid overlap
    min_gap = 3  # Minimum weeks between labels to prevent overlap

    for idx, week_start in enumerate(week_starts):
        month_key = (week_start.year, week_start.month)
        if month_key != current_month:
            current_month = month_key
            # Only add label if it's far enough from the last one
            if idx - last_label_idx >= min_gap:
                month_positions[idx] = week_start.strftime("%b %Y")
                last_label_idx = idx

    # Calculate proper dimensions for square cells
    # To get perfect squares, we need to match the aspect ratio of the axes to the plot dimensions
    # Each cell should occupy the same physical space in both x and y directions
    cell_width_px = 26  # Physical pixels per cell in x direction
    cell_height_px = (
        26  # Physical pixels per cell in y direction (same as width for squares)
    )

    # Calculate plot dimensions based on number of weeks and days
    plot_width = max(
        1400, num_weeks * cell_width_px + 260
    )  # Extra space for margins and legend
    plot_height = 5 * cell_height_px + 120  # 5 weekdays plus margins

    # Update layout with month labels and light theme
    fig.update_layout(
        title=dict(
            text=title, font=dict(size=20, family="Inter, sans-serif", color="#111827")
        ),
        xaxis=dict(
            title="",
            showgrid=False,
            zeroline=False,
            tickmode="array",
            tickvals=list(month_positions.keys()),
            ticktext=list(month_positions.values()),
            tickangle=0,
            side="top",  # Month labels at top like GitHub
            tickfont=dict(size=11, family="Inter, sans-serif", color="#6b7280"),
            scaleanchor="y",
            scaleratio=1,
            constrain="domain",
        ),
        yaxis=dict(
            title="",
            showgrid=False,
            zeroline=False,
            tickmode="array",
            tickvals=[0, 1, 2, 3, 4],
            ticktext=["Fri", "Thu", "Wed", "Tue", "Mon"],
            tickfont=dict(size=11, family="Inter, sans-serif", color="#6b7280"),
            fixedrange=True,  # Prevent zooming
            constrain="domain",
        ),
        width=plot_width,
        height=plot_height,
        hovermode="closest",
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Inter, sans-serif", color="#374151"),
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1.0,
            xanchor="left",
            x=1.02,
            font=dict(size=11),
            bgcolor="rgba(255, 255, 255, 0.9)",
            bordercolor="#e5e7eb",
            borderwidth=1,
        ),
        margin=dict(l=60, r=200, t=60, b=40),
    )

    return fig


def compute_weekly_project_allocation(schedule: Schedule, num_weeks: int) -> pd.DataFrame:
    """Compute weekly project allocation percentages with smoothing.

    Args:
        schedule: Schedule object to analyze
        num_weeks: Number of weeks to analyze

    Returns:
        DataFrame with columns: week_number, week_end_date, project_name, percent_allocated (smoothed)
    """
    if not schedule.start_date:
        return pd.DataFrame()

    # Build weekly allocation data
    weekly_data = []
    current_week_start = schedule.start_date

    for week_num in range(num_weeks):
        # Count slots per project in this week
        project_slots = {}
        total_slots = 0
        last_weekday = current_week_start  # Track the last weekday in this week

        # Iterate through each day in the week
        for day_offset in range(7):
            current_date = current_week_start + timedelta(days=day_offset)

            # Skip weekends
            if current_date.weekday() >= 5:
                continue

            # Update last weekday
            last_weekday = current_date

            # Count slots for this day
            day_slots = schedule.get_slots_for_date(current_date)

            if day_slots:
                total_slots += 1
                for slot in day_slots:
                    if slot.project is not None:
                        project_name = slot.project.name
                        if project_name not in project_slots:
                            project_slots[project_name] = 0
                        project_slots[project_name] += 1
            else:
                # If no slots exist for this date, assume 1 unscheduled slot
                total_slots += 1

        # Convert to percentages
        for project_name, count in project_slots.items():
            percent = (count / total_slots * 100) if total_slots > 0 else 0.0
            weekly_data.append({
                "week_number": week_num,
                "week_end_date": last_weekday,  # Use end of week for x-axis
                "project_name": project_name,
                "percent_allocated": percent,
            })

        # Move to next week
        current_week_start += timedelta(weeks=1)

    # Create DataFrame
    df = pd.DataFrame(weekly_data)

    if df.empty:
        return df

    # Apply 4-week rolling average smoothing per project (trailing average)
    smoothed_data = []
    for project_name in df["project_name"].unique():
        project_df = df[df["project_name"] == project_name].copy()
        project_df = project_df.sort_values("week_number")

        # Create a series with all weeks (fill missing with 0)
        all_weeks = pd.Series(0.0, index=range(num_weeks))
        week_end_dates = {}
        for _, row in project_df.iterrows():
            all_weeks[row["week_number"]] = row["percent_allocated"]
            week_end_dates[row["week_number"]] = row["week_end_date"]

        # Apply trailing rolling average (looks at current week and 3 previous weeks)
        # This prevents future data from leaking into the past
        smoothed = all_weeks.rolling(window=4, center=False, min_periods=1).mean()

        # Add back to dataframe - need to compute week_end_date for all weeks
        current_week_start = schedule.start_date
        for week_num in range(num_weeks):
            # Calculate the last weekday of this week
            week_end = current_week_start
            for day_offset in range(7):
                d = current_week_start + timedelta(days=day_offset)
                if d.weekday() < 5:  # Weekday
                    week_end = d

            smoothed_data.append({
                "week_number": week_num,
                "week_end_date": week_end,
                "project_name": project_name,
                "percent_allocated": smoothed[week_num],
            })
            current_week_start += timedelta(weeks=1)

    return pd.DataFrame(smoothed_data)


def create_project_allocation_plot(schedule: Schedule, num_weeks: int) -> Optional[go.Figure]:
    """Create stacked area plot showing weekly project allocation percentages.

    Args:
        schedule: Schedule object to visualize
        num_weeks: Number of weeks to analyze

    Returns:
        Plotly Figure object or None if no data
    """
    # Get allocation data
    df = compute_weekly_project_allocation(schedule, num_weeks)

    if df.empty:
        return None

    # Calculate total allocation for first month (4 weeks) for each project
    first_month_df = df[df["week_number"] < 4]
    project_totals = first_month_df.groupby("project_name")["percent_allocated"].sum().sort_values(ascending=False)

    # Order projects by first month allocation (descending, so largest will be at bottom of stack)
    projects = project_totals.index.tolist()

    dates = sorted(df["week_end_date"].unique())

    # Generate colors using the same HSL approach as calendar heatmap
    num_projects = len(projects)
    colors = []
    for i in range(num_projects):
        hue = (i * 360 / max(num_projects, 1)) % 360
        rgb = _hsl_to_rgb(hue, 65, 45)
        hex_color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        colors.append(hex_color)

    # Create figure
    fig = go.Figure()

    # Add each project as a stacked area (in reverse order so largest is at bottom)
    for i, project_name in enumerate(reversed(projects)):
        project_df = df[df["project_name"] == project_name].sort_values("week_end_date")
        color_idx = len(projects) - 1 - i  # Reverse color index to match original colors

        fig.add_trace(
            go.Scatter(
                x=project_df["week_end_date"],
                y=project_df["percent_allocated"],
                mode="lines",
                name=project_name,
                line=dict(width=0),
                fillcolor=colors[color_idx],
                stackgroup="one",
                groupnorm="",  # Don't normalize, use raw percentages
                hovertemplate=f"<b>{project_name}</b><br>%{{y:.1f}}%<extra></extra>",
            )
        )

    # Create month boundaries for vertical lines
    # Draw line at the first day of each month
    if not dates:
        return None

    start_date = min(dates)
    end_date = max(dates)

    month_boundaries = []
    current = date(start_date.year, start_date.month, 1)
    # Move to first day of next month
    if current < start_date:
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    while current <= end_date:
        month_boundaries.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    # Add vertical lines at month boundaries
    for boundary in month_boundaries:
        fig.add_vline(
            x=boundary,
            line_width=1,
            line_dash="dash",
            line_color="#d1d5db",
            opacity=0.6,
        )

    fig.update_layout(
        title=dict(
            text="Weekly Project Allocation",
            font=dict(size=20, family="Inter, sans-serif", color="#111827"),
        ),
        xaxis_title="",
        yaxis_title="Time Allocation (%)",
        hovermode="closest",  # Show only hovered project
        height=450,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Inter, sans-serif", color="#374151"),
        yaxis=dict(
            range=[0, 100],
            gridcolor="#f3f4f6",
            showgrid=True,
            tickfont=dict(size=12, color="#6b7280"),
        ),
        xaxis=dict(
            tickformat="%b\n%Y",
            dtick="M1",  # Monthly ticks
            ticklabelmode="period",
            gridcolor="#f3f4f6",
            showgrid=True,
            tickfont=dict(size=12, color="#6b7280"),
        ),
        legend=dict(
            orientation="v",
            yanchor="top",
            y=0.98,
            xanchor="left",
            x=1.02,
            font=dict(size=11),
            bgcolor="rgba(255, 255, 255, 0.9)",
            bordercolor="#e5e7eb",
            borderwidth=1,
        ),
        margin=dict(l=60, r=250, t=80, b=80),
        autosize=True,
    )

    return fig


def create_availability_plot(
    paced_availability: list[dict], frontload_availability: list[dict]
) -> go.Figure:
    """Create weekly coverage comparison plot with smoothing.

    Args:
        paced_availability: Weekly availability stats for paced method
        frontload_availability: Weekly availability stats for frontload method

    Returns:
        Plotly Figure object
    """
    fig = go.Figure()

    # Paced method - convert to coverage and calculate smoothed values
    paced_dates = [w["start_date"] for w in paced_availability]
    paced_percents = [100 - w["percent_available"] for w in paced_availability]

    # Create pandas series for smoothing
    paced_series = pd.Series(paced_percents)
    paced_smoothed = (
        paced_series.rolling(window=4, center=True, min_periods=1).mean().tolist()
    )

    fig.add_trace(
        go.Scatter(
            x=paced_dates,
            y=paced_smoothed,
            mode="lines",
            name="Paced Method",
            line=dict(
                color="#3b82f6", width=3, shape="spline", smoothing=1.0
            ),  # Modern blue with spline smoothing
            hovertemplate="%{x|%b %d, %Y}<br>Coverage: %{y:.1f}%<extra></extra>",
        )
    )

    # Frontload method - convert to coverage and calculate smoothed values
    frontload_dates = [w["start_date"] for w in frontload_availability]
    frontload_percents = [100 - w["percent_available"] for w in frontload_availability]

    # Create pandas series for smoothing
    frontload_series = pd.Series(frontload_percents)
    frontload_smoothed = (
        frontload_series.rolling(window=4, center=True, min_periods=1).mean().tolist()
    )

    fig.add_trace(
        go.Scatter(
            x=frontload_dates,
            y=frontload_smoothed,
            mode="lines",
            name="Frontload Method",
            line=dict(
                color="#f59e0b", width=3, shape="spline", smoothing=1.0
            ),  # Modern amber with spline smoothing
            hovertemplate="%{x|%b %d, %Y}<br>Coverage: %{y:.1f}%<extra></extra>",
        )
    )

    # Create month boundaries for vertical lines
    month_boundaries = []
    current_month = None
    for w in paced_availability:
        date_obj = w["start_date"]
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
            line_color="#d1d5db",
            opacity=0.6,
        )

    fig.update_layout(
        title=dict(
            text="Weekly Coverage Percentage",
            font=dict(size=20, family="Inter, sans-serif", color="#111827"),
        ),
        xaxis_title="",
        yaxis_title="Coverage (%)",
        hovermode="x unified",
        height=450,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Inter, sans-serif", color="#374151"),
        yaxis=dict(
            range=[0, 100],
            gridcolor="#f3f4f6",
            showgrid=True,
            tickfont=dict(size=12, color="#6b7280"),
        ),
        xaxis=dict(
            tickformat="%b\n%Y",
            dtick="M1",  # Monthly ticks
            ticklabelmode="period",
            gridcolor="#f3f4f6",
            showgrid=True,
            tickfont=dict(size=12, color="#6b7280"),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.2,
            xanchor="center",
            x=0.5,
            font=dict(size=12),
        ),
        margin=dict(l=60, r=40, t=80, b=80),
        autosize=True,
    )

    return fig
