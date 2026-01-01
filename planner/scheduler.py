"""Project scheduling algorithm."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from planner.models import Project, Schedule, ScheduledSlot, DEFAULT_COLORS


@dataclass
class ProjectStats:
    """Statistics for a project in the schedule."""

    project: Project
    total_slots_assigned: int
    slots_per_week: float
    days_per_week: float
    last_scheduled_date: Optional[date]

    @property
    def fully_scheduled(self) -> bool:
        """Check if all remaining work is scheduled."""
        return self.total_slots_assigned >= self.project.slots_remaining


class Scheduler:
    """Schedule projects based on remaining work and deadlines.

    The scheduling algorithm:
    1. Iterates through each 4-hour slot (2 per day)
    2. Assigns projects proportionally based on remaining days
    3. Ensures each project is worked on at least once every 2 weeks
    4. Supports half-day (4-hour) scheduling for smaller projects
    """

    # Maximum gap between working on the same project (in slots, 2 weeks = 28 slots)
    MAX_GAP_SLOTS = 28  # 14 days * 2 slots per day

    def __init__(self, projects: list[Project], start_date: Optional[date] = None):
        """Initialize the scheduler.

        Args:
            projects: List of projects to schedule
            start_date: Starting date for scheduling (defaults to today)
        """
        self.projects = projects
        self.start_date = start_date or date.today()
        self._assign_colors()

    def _assign_colors(self) -> None:
        """Assign colors to projects that don't have one."""
        for i, project in enumerate(self.projects):
            if project.color is None:
                project._color_index = i
                project.color = DEFAULT_COLORS[i % len(DEFAULT_COLORS)]

    def _calculate_weights(self, remaining_work: dict[Project, int]) -> dict[Project, float]:
        """Calculate scheduling weights based on remaining work.

        Projects with more remaining work get proportionally more slots.
        """
        total_remaining = sum(remaining_work.values())
        if total_remaining == 0:
            return {p: 0.0 for p in remaining_work}

        return {p: r / total_remaining for p, r in remaining_work.items()}

    def _get_most_urgent_project(
        self,
        current_date: date,
        remaining_work: dict[Project, int],
        last_scheduled: dict[Project, int],
        current_slot: int,
    ) -> Optional[Project]:
        """Select the next project to schedule.

        Priority order:
        1. Projects that haven't been worked on in 2 weeks (urgency)
        2. Projects with most remaining work (proportionality)
        """
        candidates = [p for p, r in remaining_work.items() if r > 0]
        if not candidates:
            return None

        # Check for projects that need to be worked on (2-week rule)
        urgent = []
        for project in candidates:
            slots_since_last = current_slot - last_scheduled.get(project, -self.MAX_GAP_SLOTS)
            if slots_since_last >= self.MAX_GAP_SLOTS:
                # Calculate urgency score: higher means more urgent
                urgency = slots_since_last + remaining_work[project]
                urgent.append((project, urgency))

        if urgent:
            # Sort by urgency (descending) and return most urgent
            urgent.sort(key=lambda x: x[1], reverse=True)
            return urgent[0][0]

        # No urgent projects, use weighted selection based on remaining work
        weights = self._calculate_weights(remaining_work)

        # Find project with highest weight that has work remaining
        best_project = None
        best_score = -1.0

        for project in candidates:
            # Score combines weight with time since last scheduled
            slots_since = current_slot - last_scheduled.get(project, -1)
            score = weights[project] * (1 + slots_since * 0.1)
            if score > best_score:
                best_score = score
                best_project = project

        return best_project

    def create_schedule(self, num_weeks: int = 12) -> Schedule:
        """Create a schedule for the specified number of weeks.

        Args:
            num_weeks: Number of weeks to plan ahead

        Returns:
            Schedule with assigned slots
        """
        schedule = Schedule()
        schedule.start_date = self.start_date
        schedule.end_date = self.start_date + timedelta(weeks=num_weeks)

        # Track remaining work for each project (in slots)
        remaining_work = {p: p.slots_remaining for p in self.projects}

        # Track when each project was last scheduled (slot index)
        last_scheduled: dict[Project, int] = {}

        # Generate slots for each day
        num_days = num_weeks * 7
        slot_index = 0

        for day_offset in range(num_days):
            current_date = self.start_date + timedelta(days=day_offset)

            # Skip weekends
            if current_date.weekday() >= 5:
                continue

            # Create two slots per day (AM and PM)
            for slot_of_day in range(2):
                slot = ScheduledSlot(date=current_date, slot_index=slot_of_day)

                # Find the best project for this slot
                project = self._get_most_urgent_project(
                    current_date, remaining_work, last_scheduled, slot_index
                )

                if project:
                    slot.project = project
                    remaining_work[project] -= 1
                    last_scheduled[project] = slot_index

                schedule.slots.append(slot)
                slot_index += 1

        return schedule

    def get_statistics(self, schedule: Schedule) -> list[ProjectStats]:
        """Calculate statistics for each project in the schedule.

        Returns:
            List of ProjectStats for each project
        """
        stats = []
        num_weeks = (schedule.end_date - schedule.start_date).days / 7 if schedule.end_date and schedule.start_date else 1

        for project in self.projects:
            project_slots = schedule.get_project_slots(project)
            total_slots = len(project_slots)

            # Find last scheduled date
            last_date = None
            if project_slots:
                last_date = max(s.date for s in project_slots)

            stats.append(
                ProjectStats(
                    project=project,
                    total_slots_assigned=total_slots,
                    slots_per_week=total_slots / num_weeks if num_weeks > 0 else 0,
                    days_per_week=total_slots / (2 * num_weeks) if num_weeks > 0 else 0,
                    last_scheduled_date=last_date,
                )
            )

        return stats
