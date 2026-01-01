"""Tile visualization for project schedules."""

from datetime import date, timedelta
from typing import Optional

from planner.models import Schedule, Project, RESET_COLOR


def render_tiles(schedule: Schedule, show_legend: bool = True) -> str:
    """Render the schedule as a GitHub-style tile visualization.

    Each day shows as a tile with the project's color.
    If a day has two different projects, it shows as a split tile.

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
                lines.append(f"  {block} {project.name}")
            lines.append(f"  ░░ Unassigned")
            lines.append("")

    # Header with week markers
    lines.append(_render_header(start_date, end_date))

    # Render weeks (7 rows, one per day of week)
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    for day_of_week in range(7):
        row = f"{day_names[day_of_week]:<3} "
        current_date = start_date

        # Adjust to start from the correct day of week
        while current_date.weekday() != day_of_week:
            if current_date.weekday() > day_of_week:
                # Need to go to next week
                current_date = current_date + timedelta(days=(7 - current_date.weekday() + day_of_week))
                break
            current_date = current_date + timedelta(days=1)

        # If we went past start, need to find first occurrence
        if current_date > end_date:
            # Start from beginning and find first day_of_week
            current_date = start_date
            days_ahead = day_of_week - current_date.weekday()
            if days_ahead < 0:
                days_ahead += 7
            current_date = current_date + timedelta(days=days_ahead)

        # Add leading spaces for partial first week
        first_date = start_date
        days_until = (current_date - first_date).days
        weeks_offset = days_until // 7
        if current_date.weekday() < first_date.weekday():
            weeks_offset = 0
        elif current_date < first_date:
            weeks_offset = 0

        # Find proper starting position
        if start_date.weekday() > day_of_week:
            # This day of week hasn't occurred yet in first week
            row += "  "  # Empty space for missing first week

        while current_date <= end_date:
            slots = schedule.get_slots_for_date(current_date)

            if slots:
                tile = _render_day_tile(slots)
            else:
                # Weekend or no slots
                tile = "  "

            row += tile
            current_date = current_date + timedelta(days=7)

        lines.append(row)

    return "\n".join(lines)


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


def render_statistics(stats: list, schedule: Schedule) -> str:
    """Render statistics summary for the schedule.

    Args:
        stats: List of ProjectStats
        schedule: The schedule

    Returns:
        String representation of statistics
    """
    lines = []
    lines.append("=" * 60)
    lines.append("PROJECT STATISTICS")
    lines.append("=" * 60)
    lines.append("")

    # Key statistic: When will work run out?
    last_work_date = schedule.get_last_work_date()
    if last_work_date:
        lines.append(f"📅 Work scheduled until: {last_work_date.strftime('%Y-%m-%d')} ({last_work_date.strftime('%A')})")
        days_of_work = (last_work_date - date.today()).days
        if days_of_work > 0:
            lines.append(f"   ({days_of_work} days of scheduled work)")
        lines.append("")

    # Per-project statistics
    lines.append("Days per week by project:")
    lines.append("-" * 40)

    for stat in sorted(stats, key=lambda s: s.days_per_week, reverse=True):
        project = stat.project
        color = project.color or ""
        block = f"{color}██{RESET_COLOR}"

        status = "✓" if stat.fully_scheduled else "○"
        lines.append(
            f"  {block} {project.name:<20} {stat.days_per_week:.1f} days/week  "
            f"({stat.total_slots_assigned} slots) {status}"
        )

        if stat.last_scheduled_date:
            lines.append(f"      Last scheduled: {stat.last_scheduled_date.strftime('%Y-%m-%d')}")

    lines.append("")
    lines.append("Legend: ✓ = fully scheduled, ○ = partially scheduled")

    return "\n".join(lines)
