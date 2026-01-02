"""Tile visualization for project schedules."""

from datetime import date, timedelta
from typing import Optional
from dataclasses import dataclass

from planner.models import Schedule, Project, RESET_COLOR


@dataclass
class WeeklyAvailability:
    """Availability statistics for a single week.

    Attributes:
        week_number: Week number (0-indexed from start of schedule)
        start_date: First date of the week
        total_slots: Total available work slots in the week (excludes weekends)
        unscheduled_slots: Number of slots without assigned projects
        percent_available: Percentage of slots that are unscheduled (0-100)
    """
    week_number: int
    start_date: date
    total_slots: int
    unscheduled_slots: int

    @property
    def percent_available(self) -> float:
        """Calculate percentage of unscheduled slots."""
        if self.total_slots == 0:
            return 100.0
        return (self.unscheduled_slots / self.total_slots) * 100.0


def compute_weekly_availability(schedule: Schedule, num_weeks: int) -> list[WeeklyAvailability]:
    """Compute availability percentage for each week in the schedule.

    Args:
        schedule: The schedule to analyze
        num_weeks: Number of weeks in the planning horizon

    Returns:
        List of WeeklyAvailability objects, one per week
    """
    if not schedule.start_date:
        return []

    weekly_stats = []
    current_week_start = schedule.start_date

    for week_num in range(num_weeks):
        # Calculate the date range for this week
        week_end = current_week_start + timedelta(days=6)

        # Count slots in this week
        total_slots = 0
        unscheduled_slots = 0

        # Iterate through each day in the week
        for day_offset in range(7):
            current_date = current_week_start + timedelta(days=day_offset)

            # Skip weekends (Saturday=5, Sunday=6)
            if current_date.weekday() >= 5:
                continue

            # Count slots for this day (always 2 slots per weekday: AM and PM)
            day_slots = schedule.get_slots_for_date(current_date)

            if not day_slots:
                # If no slots exist for this date, assume 2 unscheduled slots
                total_slots += 2
                unscheduled_slots += 2
            else:
                # We always have 2 slots per weekday
                total_slots += 2

                # Check which slots are scheduled
                has_am = any(s.slot_index == 0 and s.project is not None for s in day_slots)
                has_pm = any(s.slot_index == 1 and s.project is not None for s in day_slots)

                # Count unscheduled slots
                if not has_am:
                    unscheduled_slots += 1
                if not has_pm:
                    unscheduled_slots += 1

        weekly_stats.append(WeeklyAvailability(
            week_number=week_num,
            start_date=current_week_start,
            total_slots=total_slots,
            unscheduled_slots=unscheduled_slots,
        ))

        # Move to next week
        current_week_start += timedelta(weeks=1)

    return weekly_stats


def render_tiles(schedule: Schedule, show_legend: bool = True) -> str:
    """Render the schedule as a GitHub-style tile visualization.

    Each day shows as a tile with the project's color.
    Includes spacing between days, weeks, and months for better readability.

    Args:
        schedule: The schedule to visualize
        show_legend: Whether to show the color legend

    Returns:
        String representation of the tile view
    """
    if not schedule.slots:
        return "No schedule to display."

    lines = []

    # Get date range
    dates = schedule.get_unique_dates()
    if not dates:
        return "No dates in schedule."

    start_date = dates[0]
    end_date = dates[-1]

    # Build legend
    if show_legend:
        projects = set()
        for slot in schedule.slots:
            if slot.project:
                projects.add(slot.project)

        if projects:
            lines.append("Legend:")
            for project in sorted(projects, key=lambda p: p.name):
                block = f"{project.color}██{RESET_COLOR}"
                renewal_indicator = " (Renewal)" if project.is_renewal else ""
                lines.append(f"  {block} {project.name}{renewal_indicator}")
            lines.append(f"  ░░ Unassigned")
            lines.append("")

    # Render month headers and calendar grid
    lines.extend(_render_calendar_grid(schedule, start_date, end_date))

    return "\n".join(lines)


def _render_calendar_grid(schedule: Schedule, start_date: date, end_date: date) -> list[str]:
    """Render the calendar grid with month labels and spacing.

    Returns:
        List of output lines
    """
    lines = []

    # Build a list of all dates in the range
    all_dates = []
    current = start_date
    while current <= end_date:
        all_dates.append(current)
        current = current + timedelta(days=1)

    if not all_dates:
        return lines

    # Render month header
    month_header = "    "  # Align with day names
    prev_month = None
    for i, d in enumerate(all_dates):
        # Add spacing before this date
        if i > 0:
            prev_date = all_dates[i - 1]
            # Larger spacing at month boundaries
            if d.month != prev_date.month:
                month_header += "  "  # Month boundary spacing
            # Small spacing between weeks (Monday)
            elif d.weekday() == 0:
                month_header += " "  # Week boundary spacing
            else:
                month_header += ""  # Day boundary (tile includes spacing)

        # Show month label at start of each month
        if d.month != prev_month:
            month_header += d.strftime("%b")[:3]
            prev_month = d.month
            # Pad to align with tiles
            month_header += " " * (len(all_dates) // 30)  # Rough estimate
        else:
            month_header += "  "  # Two chars per tile

    lines.append(month_header)

    # Render day-of-week rows
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    for day_of_week in range(7):
        row = f"{day_names[day_of_week]:<3} "

        prev_month = None
        for i, d in enumerate(all_dates):
            # Skip if this date is not the current day of week
            if d.weekday() != day_of_week:
                continue

            # Add spacing before this tile
            if prev_month is not None:
                # Larger spacing at month boundaries
                if d.month != prev_month:
                    row += "  "  # Month boundary spacing
                # Small spacing between weeks
                elif i > 0 and all_dates[i - 1].weekday() == 6:
                    row += " "  # Week boundary spacing

            prev_month = d.month

            # Render the tile
            slots = schedule.get_slots_for_date(d)
            if slots:
                tile = _render_day_tile(slots)
            else:
                # Weekend or no slots
                tile = "  "

            row += tile + " "  # Add tiny space after each day

        lines.append(row)

    return lines


def _render_header(start_date: date, end_date: date) -> str:
    """Render the week header with month markers."""
    header = "    "  # Align with day names

    current = start_date
    last_month = None

    while current <= end_date:
        if current.month != last_month:
            header += current.strftime("%b")[0]
            last_month = current.month
        else:
            header += " "

        # Move to next week
        current = current + timedelta(days=7)

    return header


def _render_day_tile(slots: list) -> str:
    """Render a single day tile based on its slots.

    Returns a 2-character tile representation:
    - Both slots same project: ██ (full color)
    - Different projects: █▓ (split colors)
    - One slot unassigned: █░ (partial)
    - Both unassigned: ░░ (empty)
    """
    if not slots:
        return "░░"

    # Sort slots by slot_index
    slots = sorted(slots, key=lambda s: s.slot_index)

    am_project = None
    pm_project = None

    for slot in slots:
        if slot.slot_index == 0:
            am_project = slot.project
        else:
            pm_project = slot.project

    # Generate the tile
    if am_project and pm_project:
        if am_project == pm_project:
            # Full day, same project
            return f"{am_project.color}██{RESET_COLOR}"
        else:
            # Split day, different projects
            return f"{am_project.color}█{RESET_COLOR}{pm_project.color}█{RESET_COLOR}"
    elif am_project:
        return f"{am_project.color}█{RESET_COLOR}░"
    elif pm_project:
        return f"░{pm_project.color}█{RESET_COLOR}"
    else:
        return "░░"


def render_availability_plot(
    paced_availability: list[WeeklyAvailability],
    frontload_availability: list[WeeklyAvailability],
    plot_width: int = 100,
    plot_height: int = 15
) -> str:
    """Render an ASCII line plot showing availability over time for both methods.

    Args:
        paced_availability: Weekly availability stats for paced method
        frontload_availability: Weekly availability stats for frontload method
        plot_width: Width of the plot in characters
        plot_height: Height of the plot in characters

    Returns:
        String representation of the availability plot
    """
    if not paced_availability and not frontload_availability:
        return "No availability data to plot."

    lines = []
    lines.append("")
    lines.append("📈 AVAILABILITY OVER TIME")
    lines.append("=" * 60)
    lines.append("")

    # Determine number of weeks
    num_weeks = max(
        len(paced_availability) if paced_availability else 0,
        len(frontload_availability) if frontload_availability else 0
    )

    if num_weeks == 0:
        return "No weeks to plot."

    # Create a 2D grid for the plot
    grid = [[' ' for _ in range(plot_width)] for _ in range(plot_height)]

    # Helper function to map week to x coordinate
    def week_to_x(week_num: int) -> int:
        if num_weeks <= 1:
            return plot_width // 2
        return int((week_num / (num_weeks - 1)) * (plot_width - 1))

    # Helper function to map percentage to y coordinate (inverted: 100% at top, 0% at bottom)
    def percent_to_y(percent: float) -> int:
        return int(((100.0 - percent) / 100.0) * (plot_height - 1))

    # Plot paced method line (using 'P' markers)
    for i, week_stat in enumerate(paced_availability):
        x = week_to_x(i)
        y = percent_to_y(week_stat.percent_available)
        if 0 <= x < plot_width and 0 <= y < plot_height:
            grid[y][x] = 'P'

    # Plot frontload method line (using 'F' markers)
    for i, week_stat in enumerate(frontload_availability):
        x = week_to_x(i)
        y = percent_to_y(week_stat.percent_available)
        if 0 <= x < plot_width and 0 <= y < plot_height:
            # If both methods have same point, use 'B' (both)
            if grid[y][x] == 'P':
                grid[y][x] = 'B'
            else:
                grid[y][x] = 'F'

    # Draw the grid with axes
    # Top border (100%)
    lines.append("100% │" + "─" * plot_width)

    # Plot rows
    for y in range(plot_height):
        percent = 100 - (y / (plot_height - 1)) * 100
        row = ''.join(grid[y])

        # Add y-axis label every few rows
        if y == 0:
            label = "100%"
        elif y == plot_height - 1:
            label = "  0%"
        elif y == plot_height // 2:
            label = " 50%"
        else:
            label = "    "

        lines.append(f"{label:>4} │{row}│")

    # Bottom border (0%)
    lines.append("  0% │" + "─" * plot_width)

    # X-axis labels
    x_axis = "     └"
    week_labels = []

    # Add week markers
    if num_weeks <= 10:
        # Show every week
        for w in range(num_weeks):
            x_pos = week_to_x(w)
            week_labels.append((x_pos, f"W{w+1}"))
    else:
        # Show every 5th week
        for w in range(0, num_weeks, 5):
            x_pos = week_to_x(w)
            week_labels.append((x_pos, f"W{w+1}"))

    # Build x-axis line with labels
    x_axis_line = [' '] * plot_width
    for x_pos, label in week_labels:
        if x_pos < plot_width:
            x_axis_line[x_pos] = '┬'

    lines.append("     └" + ''.join(x_axis_line) + "┘")

    # Add week labels below
    label_line = ' ' * 6
    for x_pos, label in week_labels:
        # Position the label centered at x_pos
        padding = x_pos - len(label_line) + 6
        if padding > 0:
            label_line += ' ' * padding
        label_line += label

    lines.append(label_line)

    # Legend
    lines.append("")
    lines.append("Legend: P = Paced method  |  F = Frontload method  |  B = Both")
    lines.append("")

    return "\n".join(lines)


def render_statistics(stats: list, schedule: Schedule) -> str:
    """Render statistics summary for the schedule.

    Args:
        stats: List of ProjectStats
        schedule: The schedule

    Returns:
        String representation of statistics
    """
    from rich.console import Console
    from rich.table import Table
    from rich import box
    from io import StringIO

    # Create a string buffer to capture Rich output
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=True, width=80)

    # Key statistic: When will work run out?
    last_work_date = schedule.get_last_work_date()
    if last_work_date:
        days_of_work = (last_work_date - date.today()).days
        console.print(f"[bold cyan]Work scheduled until:[/bold cyan] {last_work_date.strftime('%Y-%m-%d')} ({last_work_date.strftime('%A')})")
        if days_of_work > 0:
            console.print(f"[dim]({days_of_work} days of scheduled work)[/dim]")
        console.print()

    # Per-project statistics table
    table = Table(title="Project Statistics", box=box.SIMPLE)
    table.add_column("Project", style="cyan", no_wrap=True)
    table.add_column("Days/Week", justify="right", style="green")
    table.add_column("Total Slots", justify="right", style="blue")
    table.add_column("Status", justify="center", style="yellow")
    table.add_column("Last Scheduled", style="magenta")

    for stat in sorted(stats, key=lambda s: s.days_per_week, reverse=True):
        project = stat.project
        color = project.color or ""
        block = f"{color}██{RESET_COLOR}"

        status = "✓" if stat.fully_scheduled else "○"
        status_text = "[green]Complete[/green]" if stat.fully_scheduled else "[yellow]Partial[/yellow]"

        last_date = stat.last_scheduled_date.strftime('%Y-%m-%d') if stat.last_scheduled_date else "—"

        # Use plain project name (Rich will add the color styling)
        project_name = f"{block} {project.name}"

        table.add_row(
            project_name,
            f"{stat.days_per_week:.1f}",
            str(stat.total_slots_assigned),
            status_text,
            last_date
        )

    console.print(table)

    return buffer.getvalue()
