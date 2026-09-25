"""Project scheduling algorithm."""

import warnings
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from typing import Optional

from planner.holidays import is_workday
from planner.models import (
    DEFAULT_ANNUAL_SALARY_GROWTH,
    DEFAULT_COLORS,
    DEFAULT_DURATION_DAYS,
    Project,
    ReassignedDays,
    Schedule,
    ScheduledSlot,
    renewal_name,
)

# How often the paced scheduler checks for days that must be handed off
DEFAULT_REASSIGNMENT_CADENCE_DAYS = 30

# Backstop on the schedule/measure loop that solves for reassigned days. Most
# inputs settle in a handful of passes, but the loop also trims quotas back once
# the shortfall clears, so it needs room past the first feasible pass.
DEFAULT_MAX_REASSIGNMENT_ITERATIONS = 24


@lru_cache(maxsize=None)
def _count_workdays(start: date, end: date) -> int:
    """Count workdays in [start, end]. Cached: the solver re-runs many passes."""
    if end < start:
        return 0

    workdays = 0
    d = start
    while d <= end:
        if is_workday(d):
            workdays += 1
        d += timedelta(days=1)
    return workdays


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

    # Consecutive reassignment passes a project may fail to close its shortfall
    # before the solver stops shedding its days. One flat pass is normal while
    # other projects rearrange around it; two in a row means it is capacity-bound.
    STUCK_PATIENCE = 2

    def __init__(
        self,
        projects: list[Project],
        start_date: Optional[date] = None,
        annual_salary_growth: float = DEFAULT_ANNUAL_SALARY_GROWTH,
    ):
        """Initialize the scheduler.

        Args:
            projects: List of projects to schedule
            start_date: Starting date for scheduling (defaults to today)
            annual_salary_growth: Yearly raise assumed when sizing renewal years.
                A grant year is a fixed pot of money, so each renewal buys
                ``1 / (1 + growth)`` of the previous year's days.

        Raises:
            ValueError: If annual_salary_growth is <= -1 (would zero or invert the
                days a renewal year buys)
        """
        if annual_salary_growth <= -1:
            raise ValueError("annual_salary_growth must be greater than -1.")

        self.base_projects = projects  # Store original projects
        self.start_date = start_date or date.today()
        self.annual_salary_growth = annual_salary_growth
        self.projects = projects  # Will be updated with renewals during scheduling
        self._assign_colors()

    def _assign_colors(self) -> None:
        """Assign colors to projects that don't have one."""
        for i, project in enumerate(self.projects):
            if project.color is None:
                project._color_index = i
                project.color = DEFAULT_COLORS[i % len(DEFAULT_COLORS)]

    def renewal_days_for_year(self, project: Project, index: int) -> float:
        """Days a project's ``index``-th renewal year (1-based) is worth.

        A grant year funds a fixed number of dollars, so a rising salary buys
        fewer days each year: every year is the previous one divided by
        ``1 + annual_salary_growth``.

        ``renewal_days`` is the first renewal year's budget when given -- the
        discount then applies from the year after it. Without it the current
        year's ``remaining_days`` is the baseline, so the first renewal is already
        one year of growth cheaper.
        """
        factor = 1.0 / (1.0 + self.annual_salary_growth)
        if project.renewal_days is not None:
            return project.renewal_days * factor ** (index - 1)
        return project.remaining_days * factor**index

    def _generate_renewal_projects(self, num_weeks: int) -> list[Project]:
        """Generate the renewal years of every project that has them.

        A project with ``years_left`` above 1 gets one renewal per remaining year,
        chained: each year's window starts the day after the previous year ends
        (plus ``renewal_lag_days``) and runs a year from that previous end date.
        Each year is sized by ``renewal_days_for_year``. Years whose window starts
        past the planning horizon are not created, so a short horizon costs
        nothing.

        Args:
            num_weeks: Planning horizon in weeks

        Returns:
            List of all projects including generated renewals
        """
        schedule_end = self.start_date + timedelta(weeks=num_weeks)
        all_projects = list(self.base_projects)

        for project in self.base_projects:
            lag = project.renewal_lag_days or 0
            # Each renewal year hangs off the end of the year before it
            previous_end = project.end_date

            for index in range(1, project.renewal_years + 1):
                renewal_start = previous_end + timedelta(days=1 + lag)
                # A renewal year runs one year from the previous end date, so a
                # funding gap shortens the window rather than shifting it
                renewal_end = previous_end + timedelta(days=DEFAULT_DURATION_DAYS)
                previous_end = renewal_end

                if renewal_start > schedule_end:
                    break

                days = self.renewal_days_for_year(project, index)
                if days <= 0:
                    break

                all_projects.append(
                    Project(
                        name=renewal_name(project.name, index),
                        end_date=renewal_end,
                        remaining_days=days,
                        start_date=renewal_start,
                        renewal_days=None,  # Renewals don't auto-renew
                        renewal_lag_days=None,
                        is_renewal=True,
                        parent_name=project.name,
                        color=project.color,  # Use same color as parent
                        priority=project.priority,  # Inherit priority from parent
                        _color_index=project._color_index,
                    )
                )

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
        """Count workdays (weekdays excluding holidays) between start and end (inclusive)."""
        return _count_workdays(start, end)

    def _horizon_end(self, num_weeks: int) -> date:
        """Last calendar day the schedule actually covers.

        ``num_weeks`` weeks starting on ``start_date`` ends the day *before*
        ``start_date + num_weeks`` weeks. Reassignment books its close-outs on
        real iterated days, so this has to be the inclusive last day or a project
        whose deadline lands on the boundary can never be closed out.
        """
        return self.start_date + timedelta(days=num_weeks * 7 - 1)

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

    def create_schedule(
        self,
        num_weeks: int = 52,
        method: str = "paced",
        reassign_days: bool = False,
        reassignment_cadence_days: int = DEFAULT_REASSIGNMENT_CADENCE_DAYS,
        max_reassignment_iterations: int = DEFAULT_MAX_REASSIGNMENT_ITERATIONS,
    ) -> Schedule:
        """Create a schedule for the specified number of weeks.

        Args:
            num_weeks: Number of weeks to plan ahead
            method: Scheduling method - 'paced' (default) or 'frontload'
            reassign_days: Hand off only the days that cannot be booked before a
                project's deadline (paced method only)
            reassignment_cadence_days: Calendar days between reassignment checkpoints
            max_reassignment_iterations: Cap on solver passes (see
                ``_solve_paced_with_reassignment``)

        Returns:
            Schedule with assigned slots

        Raises:
            ValueError: If method is not 'paced' or 'frontload', if reassignment
                is requested for the frontload method, if the cadence is < 1, or
                if the iteration cap is < 1
        """
        if reassign_days and reassignment_cadence_days < 1:
            raise ValueError("reassignment_cadence_days must be at least 1.")
        if reassign_days and max_reassignment_iterations < 1:
            raise ValueError("max_reassignment_iterations must be at least 1.")

        if method == "paced":
            return self._create_schedule_paced(
                num_weeks,
                reassign_days=reassign_days,
                reassignment_cadence_days=reassignment_cadence_days,
                max_reassignment_iterations=max_reassignment_iterations,
            )
        elif method == "frontload":
            if reassign_days:
                raise ValueError(
                    "Day reassignment is only supported by the 'paced' method."
                )
            return self._create_schedule_frontload(num_weeks)
        else:
            raise ValueError(
                f"Unknown scheduling method: {method}. Use 'paced' or 'frontload'."
            )

    def _create_schedule_paced(
        self,
        num_weeks: int = 52,
        reassign_days: bool = False,
        reassignment_cadence_days: int = DEFAULT_REASSIGNMENT_CADENCE_DAYS,
        max_reassignment_iterations: int = DEFAULT_MAX_REASSIGNMENT_ITERATIONS,
    ) -> Schedule:
        """Create a paced schedule, optionally handing off unbookable days.

        Without reassignment this is a single pass of the token-bucket allocator.
        With it, the schedule is solved iteratively so that only days that truly
        cannot be booked are handed off (see ``_solve_paced_with_reassignment``).

        Args:
            num_weeks: Number of weeks to plan ahead
            reassign_days: Enable reassignment
            reassignment_cadence_days: Calendar days between checkpoints
            max_reassignment_iterations: Cap on solver passes

        Returns:
            Schedule with assigned slots
        """
        if not reassign_days:
            return self._paced_pass(num_weeks)

        return self._solve_paced_with_reassignment(
            num_weeks=num_weeks,
            reassignment_cadence_days=reassignment_cadence_days,
            max_reassignment_iterations=max_reassignment_iterations,
        )

    def _solve_paced_with_reassignment(
        self,
        num_weeks: int,
        reassignment_cadence_days: int,
        max_reassignment_iterations: int,
    ) -> Schedule:
        """Solve for the smallest set of days that have to be handed off.

        Reassignment must not take days this worker could still have booked, so
        the quantity cannot be decided mid-flight -- it is only knowable once a
        project reaches its deadline with budget left over. The solver therefore
        alternates between scheduling and measuring:

        1. Schedule a pass with the reassignment quotas found so far (the first
           pass has none, so it is the plain paced schedule).
        2. Measure each project that ends the horizon short of the budget it owed
           by then (see ``_due_by_horizon``). That shortfall is work nobody can
           fit.
        3. Hand off the shortfall of the *lowest-priority* projects only, then
           schedule again. Shedding low-priority work can relieve the deadline
           pressure that was crowding out higher-priority projects, so their
           shortfall is re-measured rather than assumed -- this is the knock-on
           effect that keeps the total minimal.
        4. Once no project is short, hand back any quota the schedule turned out
           not to need and try again: freeing a project's days can let it book
           more than the pass that set the quota predicted.

        Growing then trimming can revisit a quota it has already tried, so the
        leanest shortfall-free schedule seen is kept and returned rather than
        whichever pass happens to run last. ``max_reassignment_iterations`` bounds
        the search and warns only if no pass ever cleared the shortfall.

        Not every shortfall can be shed. When a project is already capacity-bound,
        the days it hands off simply displace days it would have been scheduled --
        its total stays put however much quota it is given. Those projects are
        detected (see ``STUCK_PATIENCE``) and dropped from shedding so the loop
        settles instead of inflating their quota until the cap; the leftover days
        are reported as still behind pace.

        Each pass is scored ``(days still short, days handed off)`` and the
        lexicographic best is returned, so growing and trimming can explore freely
        without a late pass undoing a good early one.

        Returns:
            The best Schedule found: fewest days left short, then fewest days
            handed off
        """
        quotas: dict[str, int] = {}
        stuck: set[str] = set()
        strikes: dict[str, int] = {}
        previous: dict[str, int] = {}
        best: Optional[Schedule] = None
        best_score: Optional[tuple[int, int]] = None

        for _ in range(max_reassignment_iterations):
            # Intermediate passes are working drafts; only warn about the one we
            # return, otherwise every discarded pass reports its own shortfalls.
            schedule = self._paced_pass(
                num_weeks,
                reassignment_cadence_days=reassignment_cadence_days,
                quotas=quotas,
                warn=False,
            )
            shortfalls = self._unbookable_days(schedule)

            score = (sum(shortfalls.values()), schedule.total_reassigned_days)
            if best_score is None or score < best_score:
                best, best_score = schedule, score

            # A project that has been given quota and is no longer closing its
            # shortfall is shedding days it would not have been scheduled anyway.
            for project, days in shortfalls.items():
                if quotas.get(project.name, 0) <= 0:
                    continue
                if days < previous.get(project.name, days + 1):
                    strikes[project.name] = 0
                    continue
                strikes[project.name] = strikes.get(project.name, 0) + 1
                if strikes[project.name] >= self.STUCK_PATIENCE:
                    stuck.add(project.name)
            previous = {project.name: days for project, days in shortfalls.items()}

            actionable = {
                project: days
                for project, days in shortfalls.items()
                if project.name not in stuck
            }
            if actionable:
                # Shed the most expendable work first and re-measure the rest
                tier = min(project.priority for project in actionable)
                for project, days in actionable.items():
                    if project.priority == tier:
                        quotas[project.name] = quotas.get(project.name, 0) + days
                continue

            if not self._trim_unneeded_quota(schedule, quotas):
                break

        if best_score is not None and best_score[0] > 0:
            warnings.warn(
                (
                    f"Day reassignment left {best_score[0]} day(s) behind pace that "
                    f"could not be handed off: the projects owing them are already "
                    f"capacity-bound, so reassigning more of their days would not "
                    f"buy back any time."
                ),
                category=UserWarning,
                stacklevel=2,
            )

        self._warn_about_final_schedule(best)
        return best

    def _trim_unneeded_quota(
        self, schedule: Schedule, quotas: dict[str, int]
    ) -> bool:
        """Hand back quota days the schedule turned out not to need.

        A quota is set from a pass that had not yet freed the project's own days.
        Once freed, the project books more than that pass predicted and scheduled
        + reassigned runs past what it owed by the horizon -- the same day counted
        twice. The overshoot comes back off the quota so the next pass sheds less.

        The caller scores every pass, so a trim that goes too far is simply not the
        pass that gets returned.

        Returns:
            True if any quota shrank (so another pass is worth running)
        """
        trimmed = False
        for project in self.projects:
            quota = quotas.get(project.name, 0)
            if quota <= 0:
                continue
            overshoot = (
                len(schedule.get_project_slots(project))
                + schedule.reassigned_days_for(project)
                - self._due_by_horizon(project, schedule.end_date)
            )
            if overshoot > 0:
                quotas[project.name] = max(0, quota - overshoot)
                trimmed = True

        return trimmed

    def _warn_about_final_schedule(self, schedule: Schedule) -> None:
        """Run the end-of-budget check against a solved schedule.

        The solver silences its intermediate passes, so the usual warning is
        re-derived here from what the returned schedule actually booked.
        """
        remaining = {
            project: max(
                0,
                project.slots_remaining
                - len(schedule.get_project_slots(project))
                - schedule.reassigned_days_for(project),
            )
            for project in self.projects
        }
        self._warn_if_projects_missed_budget_by_deadline(
            schedule=schedule, remaining_work=remaining, method="paced"
        )

    def _due_by_horizon(self, project: Project, horizon_end: date) -> int:
        """Days of a project's budget that have to be booked inside the horizon.

        A project whose deadline falls inside the horizon owes its whole budget:
        there is no later date to work on it. A project running past the horizon
        only owes the share of its budget that its own pacing rate puts inside the
        window -- the rest can still be worked after the horizon ends. Rounded
        down, so rounding never invents a day to hand off.

        Returns 0 for a project that expired before the schedule starts (stale
        data, surfaced by ``_warn_if_projects_missed_budget_by_deadline``) or that
        does not start until after the horizon.
        """
        if project.end_date < self.start_date:
            return 0

        window_start = max(self.start_date, project.start_date or self.start_date)
        if window_start > horizon_end:
            return 0

        if project.end_date <= horizon_end:
            return project.slots_remaining

        window_workdays = self._count_weekdays_inclusive(window_start, project.end_date)
        if window_workdays <= 0:
            return 0
        in_horizon = self._count_weekdays_inclusive(window_start, horizon_end)
        return int(project.slots_remaining * in_horizon / window_workdays)

    def _unbookable_days(self, schedule: Schedule) -> dict[Project, int]:
        """Find budget the horizon left unbooked.

        Measured against ``_due_by_horizon``: the whole budget for a project that
        reaches its deadline inside the horizon, and the paced share of it for one
        that runs past the horizon. Without the second case an oversubscribed plan
        whose deadlines all sit beyond the horizon reports nothing to reassign,
        even with every workday in the horizon already booked.

        Returns:
            Project -> days that neither got scheduled nor were reassigned
        """
        shortfalls: dict[Project, int] = {}
        if schedule.end_date is None:
            return shortfalls

        for project in self.projects:
            unbooked = (
                self._due_by_horizon(project, schedule.end_date)
                - len(schedule.get_project_slots(project))
                - schedule.reassigned_days_for(project)
            )
            if unbooked > 0:
                shortfalls[project] = unbooked

        return shortfalls

    def _paced_pass(
        self,
        num_weeks: int = 52,
        reassignment_cadence_days: Optional[int] = None,
        quotas: Optional[dict[str, int]] = None,
        warn: bool = True,
    ) -> Schedule:
        """Run one pass of the paced "token bucket" allocator.

        Each project accrues fractional "credit" every working day at a constant
        rate chosen so that (if capacity allows) the project completes all of its
        remaining days near its end date rather than prematurely.

        ``quotas`` maps a project name to days it must hand off in this pass.
        Those days are booked at cadence checkpoints as the project falls behind
        (so the ledger shows *when* the help is needed), and any quota still
        unbooked at the project's deadline is booked there. A project without a
        quota never sheds a day, so a pass with no quotas is the plain schedule.

        Args:
            num_weeks: Number of weeks to plan ahead
            reassignment_cadence_days: Calendar days between checkpoints
            quotas: Per-project day quotas to hand off
            warn: Warn about projects ending with unbooked budget (the solver
                silences its intermediate passes)

        Returns:
            Schedule with assigned slots
        """
        quotas = quotas or {}
        booked: dict[str, int] = {}
        if reassignment_cadence_days is None:
            reassignment_cadence_days = DEFAULT_REASSIGNMENT_CADENCE_DAYS
        schedule = Schedule()
        schedule.start_date = self.start_date
        schedule.end_date = self._horizon_end(num_weeks)

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

            # Skip weekends and holidays
            if is_workday(current_date):
                # Accrue pacing credits for active projects.
                for project in self.projects:
                    if remaining_work[project] <= 0:
                        continue
                    if (
                        project.start_date is not None
                        and current_date < project.start_date
                    ):
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

            if quotas:
                # Book quota days as the project falls behind (calendar cadence,
                # so the checkpoint still fires on a weekend or holiday).
                if (day_offset + 1) % reassignment_cadence_days == 0:
                    self._book_quota_at_checkpoint(
                        schedule=schedule,
                        checkpoint_date=current_date,
                        remaining_work=remaining_work,
                        pacing_credit=pacing_credit,
                        quotas=quotas,
                        booked=booked,
                    )
                # Any quota still unbooked at the deadline is booked there
                self._book_quota_at_deadline(
                    schedule=schedule,
                    current_date=current_date,
                    remaining_work=remaining_work,
                    pacing_credit=pacing_credit,
                    quotas=quotas,
                    booked=booked,
                )

        if quotas:
            # A project running past the horizon never hits its deadline in this
            # loop, so its quota is closed out on the last day of the horizon.
            self._book_remaining_quota(
                schedule=schedule,
                booking_date=schedule.end_date,
                remaining_work=remaining_work,
                quotas=quotas,
                booked=booked,
            )

        if warn:
            self._warn_if_projects_missed_budget_by_deadline(
                schedule=schedule, remaining_work=remaining_work, method="paced"
            )
        return schedule

    def _book_quota_at_checkpoint(
        self,
        schedule: Schedule,
        checkpoint_date: date,
        remaining_work: dict[Project, int],
        pacing_credit: dict[Project, float],
        quotas: dict[str, int],
        booked: dict[str, int],
    ) -> None:
        """Book part of a project's quota where it has fallen behind pace.

        The quota fixes *how many* days are handed off; leftover pacing credit
        says *when* the help is needed. Whole days of credit are booked, capped by
        the quota still outstanding, and removed from both the credit balance and
        the remaining budget.

        Fractional credit is left to accrue, so a project that is a fraction of a
        day behind is not charged a whole day.
        """
        for project in self.projects:
            outstanding = quotas.get(project.name, 0) - booked.get(project.name, 0)
            if outstanding <= 0:
                continue

            owed = int(pacing_credit.get(project, 0.0))
            days = min(owed, outstanding, remaining_work[project])
            if days <= 0:
                continue

            remaining_work[project] -= days
            pacing_credit[project] -= days
            booked[project.name] = booked.get(project.name, 0) + days
            schedule.reassignments.append(
                ReassignedDays(project=project, date=checkpoint_date, days=days)
            )

    def _book_quota_at_deadline(
        self,
        schedule: Schedule,
        current_date: date,
        remaining_work: dict[Project, int],
        pacing_credit: dict[Project, float],
        quotas: dict[str, int],
        booked: dict[str, int],
    ) -> None:
        """Book any quota a project has left when it reaches its deadline.

        Checkpoints only book days a project is measurably behind on, so a quota
        can still be outstanding on the end date. Those days cannot be worked by
        this worker any more, so they are booked here rather than left to expire.
        Fires once per project, on its end date.
        """
        due = [p for p in self.projects if p.end_date == current_date]
        for project in self._book_remaining_quota(
            schedule=schedule,
            booking_date=current_date,
            remaining_work=remaining_work,
            quotas=quotas,
            booked=booked,
            projects=due,
        ):
            pacing_credit[project] = 0.0

    def _book_remaining_quota(
        self,
        schedule: Schedule,
        booking_date: Optional[date],
        remaining_work: dict[Project, int],
        quotas: dict[str, int],
        booked: dict[str, int],
        projects: Optional[list[Project]] = None,
    ) -> list[Project]:
        """Book every day of quota still outstanding, on ``booking_date``.

        Used for the two points of no return: a project's deadline, and the end of
        the horizon for a project whose deadline lies beyond it. Capped by the
        budget still unbooked, so a project can never shed more than it has.

        Returns:
            The projects that had days booked
        """
        if booking_date is None:
            return []

        shed: list[Project] = []
        for project in self.projects if projects is None else projects:
            outstanding = quotas.get(project.name, 0) - booked.get(project.name, 0)
            days = min(outstanding, remaining_work[project])
            if days <= 0:
                continue

            remaining_work[project] -= days
            booked[project.name] = booked.get(project.name, 0) + days
            schedule.reassignments.append(
                ReassignedDays(project=project, date=booking_date, days=days)
            )
            shed.append(project)

        return shed

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
            scheduled = len(project_slots)
            # Reassigned days left this worker's budget, so exclude them
            budget = project.slots_remaining - schedule.reassigned_days_for(project)

            warnings.warn(
                (
                    f"[{method}] Project '{project.name}' ended on {project.end_date} "
                    f"with {remaining} day(s) of budget remaining "
                    f"({scheduled}/{budget} scheduled). "
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
            # Every project here needs all of its remaining workdays, so if more
            # than one is listed at least one of them must shed days no matter
            # what: priority picks the survivor, slack and EDD break its ties.
            must_do.sort(
                key=lambda p: (
                    -p.priority,
                    # Smallest slack first (most overdue / least flexibility)
                    self._count_weekdays_inclusive(current_date, p.end_date)
                    - remaining_work[p],
                    p.end_date,
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
            # The set as a whole is oversubscribed, so someone in it loses days:
            # again priority chooses, with slack and EDD as tie-breakers.
            forced_set.sort(
                key=lambda p: (
                    -p.priority,
                    self._count_weekdays_inclusive(current_date, p.end_date)
                    - remaining_work[p],
                    p.end_date,
                    p.name,
                )
            )
            return forced_set[0]

        # Schedule projects that are behind pace (positive credit).
        eligible = [p for p in active if pacing_credit.get(p, 0.0) > 1e-9]
        if not eligible:
            return None

        # Prefer higher priority, then the most behind (highest credit), then
        # earlier deadline. Priority must lead: pacing credit is a continuous
        # float, so any key behind it is effectively unreachable.
        #
        # Priority does not let a project hog capacity -- credit only accrues at
        # the project's own paced rate, so a high-priority project claims a slot
        # only when it is behind its own pace. Deadline feasibility still wins
        # over priority via the must-do and cumulative guards above.
        eligible.sort(
            key=lambda p: (
                -p.priority,
                -pacing_credit.get(p, 0.0),
                p.end_date,
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
        schedule.end_date = self._horizon_end(num_weeks)

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

            # Skip weekends and holidays
            if not is_workday(current_date):
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
