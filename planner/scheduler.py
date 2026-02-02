"""Project scheduling algorithm."""

import warnings
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from planner.models import DEFAULT_COLORS, Project, Schedule, ScheduledSlot


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

    Supports two scheduling methods:
    - 'paced': Balances work across projects, ensuring each project is worked on
               at least once every 2 weeks with proportional allocation
    - 'frontload': Assigns as much work as possible to each project before
                   moving to the next (concentrates work)

    Both methods:
    1. Iterate through each day slot (1 per day)
    2. Skip weekends (Monday-Friday only)
    3. Support full-day (8-hour) scheduling
    """

    # Maximum gap between working on the same project (in slots, 2 weeks = 14 slots)
    MAX_GAP_SLOTS = 14  # 14 days * 1 slot per day
    WORKDAYS_PER_WEEK = 5

    def __init__(self, projects: list[Project], start_date: Optional[date] = None):
        """Initialize the scheduler.

        Args:
            projects: List of projects to schedule
            start_date: Starting date for scheduling (defaults to today)
        """
        self.base_projects = projects  # Store original projects
        self.start_date = start_date or date.today()
        self.projects = projects  # Will be updated with renewals during scheduling
        self._assign_colors()

    def _assign_colors(self) -> None:
        """Assign colors to projects that don't have one."""
        for i, project in enumerate(self.projects):
            if project.color is None:
                project._color_index = i
                project.color = DEFAULT_COLORS[i % len(DEFAULT_COLORS)]

    def _generate_renewal_projects(self, num_weeks: int) -> list[Project]:
        """Generate renewal projects for projects with renewal_days.

        Renewals are created when:
        1. The original project has renewal_days set
        2. The original project completes within the planning horizon
        3. The renewal would start within the planning horizon

        Args:
            num_weeks: Planning horizon in weeks

        Returns:
            List of all projects including generated renewals
        """
        schedule_end = self.start_date + timedelta(weeks=num_weeks)
        all_projects = list(self.base_projects)

        for project in self.base_projects:
            if project.renewal_days is not None and project.renewal_days > 0:
                # Calculate when this project would complete
                # Assuming it starts immediately and takes remaining_days
                project_completion = project.end_date

                # Renewal starts right after project completion
                renewal_start = project_completion + timedelta(days=1)

                # Renewal lasts one year from start
                renewal_end = renewal_start + timedelta(days=365)

                # Only create renewal if it starts within the planning horizon
                if renewal_start <= schedule_end:
                    renewal = Project(
                        name=f"{project.name} (Renewal)",
                        end_date=renewal_end,
                        remaining_days=project.renewal_days,
                        start_date=renewal_start,
                        renewal_days=None,  # Renewals don't auto-renew
                        is_renewal=True,
                        parent_name=project.name,
                        color=project.color,  # Use same color as parent
                        priority=project.priority,  # Inherit priority from parent
                        _color_index=project._color_index,
                    )
                    all_projects.append(renewal)

        return all_projects

    def _calculate_weights(
        self, remaining_work: dict[Project, int]
    ) -> dict[Project, float]:
        """Calculate scheduling weights based on remaining work.

        Projects with more remaining work get proportionally more slots.
        """
        total_remaining = sum(remaining_work.values())
        if total_remaining == 0:
            return {p: 0.0 for p in remaining_work}

        return {p: r / total_remaining for p, r in remaining_work.items()}

    @staticmethod
    def _count_weekdays_inclusive(start: date, end: date) -> int:
        """Count weekdays between start and end dates (inclusive)."""
        if end < start:
            return 0

        total_days = (end - start).days + 1
        full_weeks, remainder = divmod(total_days, 7)

        weekdays = full_weeks * 5
        start_weekday = start.weekday()
        for i in range(remainder):
            if (start_weekday + i) % 7 < 5:
                weekdays += 1
        return weekdays

    def _get_most_urgent_project(
        self,
        current_date: date,
        remaining_work: dict[Project, int],
        last_scheduled: dict[Project, int],
        current_slot: int,
        current_project: Optional[Project] = None,
        consecutive_slots: int = 0,
    ) -> Optional[Project]:
        """Select the next project to schedule.

        Priority order:
        1. Continuity: Continue current project if we just started it (minimize fragmentation)
        2. Projects that haven't been worked on in 2 weeks (urgency)
        3. Projects with earliest due date (EDD)
        4. Projects with most remaining work (proportionality)

        Args:
            current_date: Current date being scheduled
            remaining_work: Dict of remaining slots per project
            last_scheduled: Dict of last slot index per project
            current_slot: Current slot index
            current_project: Project from previous slot (for continuity)
            consecutive_slots: Number of consecutive slots for current project
        """
        candidates = [p for p, r in remaining_work.items() if r > 0]
        if not candidates:
            return None

        # Continuity priority: Continue current project to minimize fragmentation
        # The bonus decreases as consecutive slots increase
        # Target: work on same project for 2-6 consecutive slots (1-3 days)
        if current_project and current_project in candidates:
            # Continuity bonus: high initially, decreases over time
            # Formula: max(0, 1.0 - consecutive_slots * 0.15)
            # This gives high priority for first 4-6 slots, then gradually decreases
            continuity_bonus = max(0, 1.0 - consecutive_slots * 0.15)

            # Apply continuity bonus if still significant
            if (
                continuity_bonus > 0.3 and consecutive_slots < 10
            ):  # Max ~1 week continuous
                # Strong bonus for continuity (higher than other factors)
                # This ensures we continue working on the same project
                return current_project

        # Check for projects that need to be worked on (2-week rule)
        urgent = []
        for project in candidates:
            slots_since_last = current_slot - last_scheduled.get(
                project, -self.MAX_GAP_SLOTS
            )
            if slots_since_last >= self.MAX_GAP_SLOTS:
                # Calculate urgency score: higher means more urgent
                # Prioritize by earliest due date (days until deadline, negative for sooner)
                days_until = (project.end_date - current_date).days
                urgency = slots_since_last + remaining_work[project] - days_until * 0.5
                urgent.append((project, urgency))

        if urgent:
            # Sort by urgency (descending) and return most urgent
            urgent.sort(key=lambda x: x[1], reverse=True)
            return urgent[0][0]

        # No urgent projects, use EDD + weighted selection
        weights = self._calculate_weights(remaining_work)

        # Find project with highest score that has work remaining
        best_project = None
        best_score = -float("inf")

        for project in candidates:
            # Score combines:
            # 1. Priority: higher priority = higher score
            # 2. EDD: earlier deadlines are prioritized (negative days until deadline)
            # 3. Weight: proportional to remaining work
            # 4. Time since last scheduled
            days_until = (project.end_date - current_date).days
            slots_since = current_slot - last_scheduled.get(project, -1)

            # Priority component (higher priority = higher score)
            priority_score = project.priority

            # EDD component (earlier deadline = higher priority)
            edd_score = -days_until / 365.0  # Normalize to 0-1 range

            # Combined score (priority has highest weight)
            score = (
                priority_score * 10.0
                + edd_score * 2.0
                + weights[project]
                + slots_since * 0.1
            )

            if score > best_score:
                best_score = score
                best_project = project

        return best_project

    def create_schedule(self, num_weeks: int = 52, method: str = "paced") -> Schedule:
        """Create a schedule for the specified number of weeks.

        Args:
            num_weeks: Number of weeks to plan ahead
            method: Scheduling method - 'paced' (default) or 'frontload'

        Returns:
            Schedule with assigned slots

        Raises:
            ValueError: If method is not 'paced' or 'frontload'
        """
        if method == "paced":
            return self._create_schedule_paced(num_weeks)
        elif method == "frontload":
            return self._create_schedule_frontload(num_weeks)
        else:
            raise ValueError(
                f"Unknown scheduling method: {method}. Use 'paced' or 'frontload'."
            )

    def _create_schedule_paced(self, num_weeks: int = 52) -> Schedule:
        """Create a paced schedule with a truly paced "token bucket" allocator.

        Each project accrues fractional "credit" every working day at a constant
        rate chosen so that (if capacity allows) the project completes all of its
        remaining days near its end date rather than prematurely.

        Args:
            num_weeks: Number of weeks to plan ahead

        Returns:
            Schedule with assigned slots
        """
        schedule = Schedule()
        schedule.start_date = self.start_date
        schedule.end_date = self.start_date + timedelta(weeks=num_weeks)

        # Generate renewal projects
        all_projects = self._generate_renewal_projects(num_weeks)
        self.projects = all_projects  # Update projects list

        # Track remaining work for each project (in full-day slots)
        remaining_work: dict[Project, int] = {
            p: p.slots_remaining for p in self.projects
        }

        # Pacing credits: accrue at a constant rate so completion lands near end_date.
        pacing_credit: dict[Project, float] = {p: 0.0 for p in self.projects}
        pacing_rate: dict[Project, float] = {}
        for project in self.projects:
            effective_start = project.start_date or self.start_date
            total_workdays = self._count_weekdays_inclusive(
                max(self.start_date, effective_start),
                project.end_date,
            )
            if remaining_work[project] <= 0 or total_workdays <= 0:
                pacing_rate[project] = 0.0
            else:
                pacing_rate[project] = remaining_work[project] / float(total_workdays)

        # Generate slots for each day
        num_days = num_weeks * 7

        for day_offset in range(num_days):
            current_date = self.start_date + timedelta(days=day_offset)

            # Skip weekends
            if current_date.weekday() >= 5:
                continue

            # Accrue pacing credits for active projects.
            for project in self.projects:
                if remaining_work[project] <= 0:
                    continue
                if project.start_date is not None and current_date < project.start_date:
                    continue
                if current_date > project.end_date:
                    continue
                pacing_credit[project] += pacing_rate[project]

            # Create one slot per day
            slot = ScheduledSlot(date=current_date)

            # Find the best project for this slot
            project = self._get_paced_project(
                current_date, remaining_work, pacing_credit
            )

            if project:
                slot.project = project
                remaining_work[project] -= 1
                pacing_credit[project] -= 1.0

            schedule.slots.append(slot)

        self._warn_if_projects_missed_budget_by_deadline(
            schedule=schedule, remaining_work=remaining_work, method="paced"
        )
        return schedule

    def _warn_if_projects_missed_budget_by_deadline(
        self, schedule: Schedule, remaining_work: dict[Project, int], method: str
    ) -> None:
        """Warn when a project reaches its end date with budget remaining.

        This helps surface infeasible schedules (or bugs) when rendering `schedule.qmd`.
        Only projects whose end dates are within the schedule horizon are checked.
        """
        if schedule.end_date is None:
            return

        for project in self.projects:
            if project.end_date > schedule.end_date:
                continue
            remaining = remaining_work.get(project, 0)
            if remaining <= 0:
                continue

            project_slots = schedule.get_project_slots(project)
            last_scheduled = max((s.date for s in project_slots), default=None)
            scheduled = project.slots_remaining - remaining

            warnings.warn(
                (
                    f"[{method}] Project '{project.name}' ended on {project.end_date} "
                    f"with {remaining} day(s) of budget remaining "
                    f"({scheduled}/{project.slots_remaining} scheduled). "
                    f"Last scheduled: {last_scheduled}."
                ),
                category=UserWarning,
                stacklevel=2,
            )

    def _get_paced_project(
        self,
        current_date: date,
        remaining_work: dict[Project, int],
        pacing_credit: dict[Project, float],
    ) -> Optional[Project]:
        """Select the next project for paced scheduling.

        Args:
            current_date: Current date being scheduled
            remaining_work: Dict of remaining full-day slots per project
            pacing_credit: Dict of accrued pacing credit per project

        Returns:
            Project to schedule, or None if no eligible project
        """
        active: list[Project] = []
        for project, remaining in remaining_work.items():
            if remaining <= 0:
                continue
            if project.start_date is not None and current_date < project.start_date:
                continue
            if current_date > project.end_date:
                continue
            active.append(project)

        if not active:
            return None

        # Hard feasibility rule: if a project needs every remaining workday, do it now.
        must_do: list[Project] = []
        for project in active:
            workdays_left = self._count_weekdays_inclusive(
                current_date, project.end_date
            )
            if workdays_left > 0 and remaining_work[project] >= workdays_left:
                must_do.append(project)

        if must_do:
            must_do.sort(
                key=lambda p: (
                    # Smallest slack first (most overdue / least flexibility)
                    self._count_weekdays_inclusive(current_date, p.end_date)
                    - remaining_work[p],
                    p.end_date,
                    -p.priority,
                    p.name,
                )
            )
            return must_do[0]

        # Cumulative feasibility guard:
        # If the remaining work due by some deadline D is >= the remaining available
        # workdays until D, then we must spend today's slot on projects due by D.
        deadlines = sorted({p.end_date for p in active})
        forced_set: Optional[list[Project]] = None
        for deadline in deadlines:
            available = self._count_weekdays_inclusive(current_date, deadline)
            if available <= 0:
                continue
            required = sum(remaining_work[p] for p in active if p.end_date <= deadline)
            if required >= available:
                forced_set = [p for p in active if p.end_date <= deadline]
                break

        if forced_set:
            forced_set.sort(
                key=lambda p: (
                    self._count_weekdays_inclusive(current_date, p.end_date)
                    - remaining_work[p],
                    p.end_date,
                    -p.priority,
                    p.name,
                )
            )
            return forced_set[0]

        # Schedule projects that are behind pace (positive credit).
        eligible = [p for p in active if pacing_credit.get(p, 0.0) > 1e-9]
        if not eligible:
            return None

        # Prefer the most behind (highest credit), then earlier deadline, then higher priority.
        eligible.sort(
            key=lambda p: (
                -pacing_credit.get(p, 0.0),
                p.end_date,
                -p.priority,
                p.name,
            )
        )
        return eligible[0]

    def _create_schedule_frontload(self, num_weeks: int = 52) -> Schedule:
        """Create a frontload schedule that concentrates work on projects.

        This method assigns as much work as possible to each project before
        moving to the next. Projects are ordered by EDD (earliest due date first),
        then by remaining work (descending).

        Args:
            num_weeks: Number of weeks to plan ahead

        Returns:
            Schedule with assigned slots
        """
        schedule = Schedule()
        schedule.start_date = self.start_date
        schedule.end_date = self.start_date + timedelta(weeks=num_weeks)

        # Generate renewal projects
        all_projects = self._generate_renewal_projects(num_weeks)
        self.projects = all_projects  # Update projects list

        # Sort projects by priority first (highest first), then EDD (earliest deadline first), then by remaining work (descending)
        sorted_projects = sorted(
            self.projects, key=lambda p: (-p.priority, p.end_date, -p.slots_remaining)
        )

        # Track remaining work for each project (in slots)
        remaining_work = {p: p.slots_remaining for p in self.projects}

        # Generate slots for each day
        num_days = num_weeks * 7

        for day_offset in range(num_days):
            current_date = self.start_date + timedelta(days=day_offset)

            # Skip weekends
            if current_date.weekday() >= 5:
                continue

            # Create one slot per day
            slot = ScheduledSlot(date=current_date)

            # Find the first project in EDD order that:
            # 1. Has remaining work
            # 2. Has started (current_date >= start_date)
            project = None
            for candidate in sorted_projects:
                if remaining_work[candidate] > 0:
                    # Check if project has started
                    if (
                        candidate.start_date is not None
                        and current_date < candidate.start_date
                    ):
                        continue
                    project = candidate
                    break

            if project:
                slot.project = project
                remaining_work[project] -= 1

            schedule.slots.append(slot)

        self._warn_if_projects_missed_budget_by_deadline(
            schedule=schedule, remaining_work=remaining_work, method="frontload"
        )
        return schedule

    def get_statistics(self, schedule: Schedule) -> list[ProjectStats]:
        """Calculate statistics for each project in the schedule.

        Returns:
            List of ProjectStats for each project
        """
        stats = []
        num_weeks = (
            (schedule.end_date - schedule.start_date).days / 7
            if schedule.end_date and schedule.start_date
            else 1
        )

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
                    days_per_week=total_slots / num_weeks
                    if num_weeks > 0
                    else 0,  # 1 slot = 1 day
                    last_scheduled_date=last_date,
                )
            )

        return stats
