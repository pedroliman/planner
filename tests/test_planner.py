"""Tests for the project planner."""

import json
import warnings
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from planner.holidays import is_workday
from planner.models import Project, Schedule, ScheduledSlot
from planner.scheduler import Scheduler

# Note: Visualization functions have been moved to schedule.qmd Quarto document
# Tests for visualization are no longer applicable as visualization is handled by Quarto


class TestProject:
    """Tests for the Project model."""

    def test_project_creation(self):
        """Test basic project creation."""
        project = Project(
            name="Test Project",
            end_date=date(2024, 12, 31),
            remaining_days=10,
        )
        assert project.name == "Test Project"
        assert project.end_date == date(2024, 12, 31)
        assert project.remaining_days == 10

    def test_slots_remaining(self):
        """Test calculation of remaining slots (1 slot per day)."""
        project = Project(
            name="Test",
            end_date=date(2024, 12, 31),
            remaining_days=5,
        )
        assert project.slots_remaining == 5  # 5 days * 1 slot

    def test_slots_remaining_fractional_day(self):
        """Test fractional day slot calculation (rounded down)."""
        project = Project(
            name="Small Project",
            end_date=date(2024, 12, 31),
            remaining_days=2.5,
        )
        assert project.slots_remaining == 2  # int(2.5) = 2 slots

    def test_days_until_deadline(self):
        """Test days until deadline calculation."""
        project = Project(
            name="Test",
            end_date=date(2024, 12, 31),
            remaining_days=5,
        )
        from_date = date(2024, 12, 1)
        assert project.days_until_deadline(from_date) == 30


class TestScheduledSlot:
    """Tests for the ScheduledSlot model."""

    def test_slot_creation(self):
        """Test slot creation with project assignment."""
        project = Project("Test", date(2024, 12, 31), 5)
        slot = ScheduledSlot(date=date(2024, 11, 1), project=project)

        assert slot.date == date(2024, 11, 1)
        assert slot.project == project

    def test_unassigned_slot(self):
        """Test slot creation without project assignment."""
        slot = ScheduledSlot(date=date(2024, 11, 1))
        assert slot.date == date(2024, 11, 1)
        assert slot.project is None


class TestSchedule:
    """Tests for the Schedule model."""

    def test_empty_schedule(self):
        """Test empty schedule."""
        schedule = Schedule()
        assert len(schedule.slots) == 0
        assert schedule.get_last_work_date() is None

    def test_get_slots_for_date(self):
        """Test getting slots for a specific date."""
        project = Project("Test", date(2024, 12, 31), 5)
        schedule = Schedule(
            slots=[
                ScheduledSlot(date(2024, 11, 1), project),
                ScheduledSlot(date(2024, 11, 2), project),
            ]
        )

        slots_nov_1 = schedule.get_slots_for_date(date(2024, 11, 1))
        assert len(slots_nov_1) == 1

        slots_nov_2 = schedule.get_slots_for_date(date(2024, 11, 2))
        assert len(slots_nov_2) == 1

    def test_get_project_slots(self):
        """Test getting all slots for a project."""
        project_a = Project("A", date(2024, 12, 31), 5)
        project_b = Project("B", date(2024, 12, 31), 3)

        schedule = Schedule(
            slots=[
                ScheduledSlot(date(2024, 11, 1), project_a),
                ScheduledSlot(date(2024, 11, 2), project_b),
                ScheduledSlot(date(2024, 11, 3), project_a),
            ]
        )

        a_slots = schedule.get_project_slots(project_a)
        assert len(a_slots) == 2

        b_slots = schedule.get_project_slots(project_b)
        assert len(b_slots) == 1

    def test_get_last_work_date(self):
        """Test finding last work date."""
        project = Project("Test", date(2024, 12, 31), 5)
        schedule = Schedule(
            slots=[
                ScheduledSlot(date(2024, 11, 1), project),
                ScheduledSlot(date(2024, 11, 5), None),  # Unassigned
                ScheduledSlot(date(2024, 11, 3), project),
            ]
        )

        assert schedule.get_last_work_date() == date(2024, 11, 3)


class TestScheduler:
    """Tests for the Scheduler."""

    def test_scheduler_creation(self):
        """Test scheduler initialization."""
        projects = [
            Project("A", date(2024, 12, 31), 10),
            Project("B", date(2024, 12, 31), 5),
        ]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 1))

        assert len(scheduler.projects) == 2
        assert scheduler.start_date == date(2024, 11, 1)

    def test_create_schedule_basic(self):
        """Test basic schedule creation."""
        projects = [
            Project("A", date(2024, 12, 31), 5),
        ]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))  # Monday
        schedule = scheduler.create_schedule(num_weeks=2)

        assert schedule.start_date == date(2024, 11, 4)
        assert len(schedule.slots) > 0

        # Should have slots for weekdays only
        for slot in schedule.slots:
            assert slot.date.weekday() < 5  # Monday-Friday

    def test_warns_when_project_ends_with_budget_remaining(self):
        """Test that we warn when a project reaches its end date with work remaining."""
        projects = [
            Project("Impossible", date(2024, 11, 8), 10),  # 5 workdays available
        ]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))  # Monday

        with pytest.warns(UserWarning, match=r"ended on"):
            scheduler.create_schedule(num_weeks=2, method="paced")

    def test_schedule_assigns_all_work(self):
        """Test that paced scheduling does not exhaust far-off work immediately."""
        projects = [
            Project("Small", date(2024, 12, 31), 2),
        ]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=4)

        project_slots = schedule.get_project_slots(projects[0])
        # With a far-off deadline, paced scheduling should defer most of the work.
        assert len(project_slots) == 1

    def test_schedule_proportional_distribution(self):
        """Test that projects get slots proportional to remaining work."""
        projects = [
            Project("Big", date(2024, 12, 31), 20),
            Project("Small", date(2024, 12, 31), 5),
        ]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=8)

        big_slots = len(schedule.get_project_slots(projects[0]))
        small_slots = len(schedule.get_project_slots(projects[1]))

        # Big project has 4x the work, should get approximately 4x the slots
        # Allow some variance due to scheduling algorithm
        ratio = big_slots / small_slots if small_slots > 0 else float("inf")
        assert 2.0 <= ratio <= 6.0  # Reasonably proportional

    def test_schedule_two_week_rule(self):
        """Test that each project is worked on at least once every 2 weeks."""
        projects = [
            Project("A", date(2024, 12, 31), 30),
            Project("B", date(2024, 12, 31), 30),
            Project("C", date(2024, 12, 31), 30),
        ]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=8)

        # Check each project
        for project in projects:
            project_slots = sorted(
                schedule.get_project_slots(project), key=lambda s: s.date
            )

            if len(project_slots) >= 2:
                # Check gap between consecutive slots
                for i in range(1, len(project_slots)):
                    prev_date = project_slots[i - 1].date
                    curr_date = project_slots[i].date
                    gap_days = (curr_date - prev_date).days
                    # Gap should be at most 14 days (2 weeks)
                    assert gap_days <= 14, f"Gap of {gap_days} days for {project.name}"

    def test_get_statistics(self):
        """Test statistics calculation."""
        projects = [
            Project("A", date(2024, 12, 31), 10),
        ]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=4)

        stats = scheduler.get_statistics(schedule)
        assert len(stats) == 1

        stat = stats[0]
        assert stat.project == projects[0]
        assert stat.total_slots_assigned > 0
        assert stat.days_per_week > 0


# NOTE: The following visualization tests have been commented out because
# visualization is now handled by the schedule.qmd Quarto document instead of Python code.
# The visualization logic has been moved to Quarto for better interactive plotting with Plotly.

# # class TestVisualization:
#     """Tests for the visualization module."""

#     def test_render_tiles_empty(self):
#         """Test rendering empty schedule."""
#         schedule = Schedule()
#         result = render_tiles(schedule)
#         assert "No schedule" in result

#     def test_render_tiles_basic(self):
#         """Test basic tile rendering."""
#         project = Project("Test", date(2024, 12, 31), 5)
#         schedule = Schedule(
#             slots=[
#                 ScheduledSlot(date(2024, 11, 4), project),
#             ],
#             start_date=date(2024, 11, 4),
#             end_date=date(2024, 11, 10),
#         )

#         result = render_tiles(schedule)
#         assert "Legend" in result
#         assert "Test" in result

#     def test_render_statistics(self):
#         """Test statistics rendering."""
#         project = Project("Test Project", date(2024, 12, 31), 5)
#         schedule = Schedule(
#             slots=[
#                 ScheduledSlot(date(2024, 11, 4), project),
#             ],
#             start_date=date(2024, 11, 4),
#             end_date=date(2024, 11, 10),
#         )

#         from planner.scheduler import ProjectStats
#         stats = [
#             ProjectStats(
#                 project=project,
#                 total_slots_assigned=1,
#                 slots_per_week=1.0,
#                 days_per_week=1.0,
#                 last_scheduled_date=date(2024, 11, 4),
#             )
#         ]

#         result = render_statistics(stats, schedule)
#         assert "Project Statistics" in result
#         assert "Test Project" in result
#         assert "Days/Week" in result


class TestIntegration:
    """Integration tests for the full workflow."""

    def test_full_planning_workflow(self):
        """Test complete planning workflow from projects to schedule generation."""
        projects = [
            Project("Alpha", date(2024, 12, 31), 15),
            Project("Beta", date(2024, 12, 15), 8),
            Project("Gamma", date(2024, 11, 30), 3),
        ]

        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
        schedule_paced = scheduler.create_schedule(num_weeks=8, method="paced")
        schedule_frontload = scheduler.create_schedule(num_weeks=8, method="frontload")

        # Verify schedule was created
        assert len(schedule_paced.slots) > 0
        assert len(schedule_frontload.slots) > 0

        # Verify statistics
        stats_paced = scheduler.get_statistics(schedule_paced)
        stats_frontload = scheduler.get_statistics(schedule_frontload)
        assert len(stats_paced) == 3
        assert len(stats_frontload) == 3

        for stat in stats_paced:
            assert stat.days_per_week >= 0

        # Frontload should complete all work (26 days total, 40 slots available)
        total_work = sum(p.remaining_days for p in projects)
        total_scheduled = sum(s.total_slots_assigned for s in stats_frontload)
        assert total_scheduled >= min(total_work, 40)

    def test_fractional_day_scheduling(self):
        """Test that fractional days are handled (rounded down to slots)."""
        projects = [
            Project("Big", date(2024, 12, 31), 5),
            Project("Tiny", date(2024, 12, 31), 2.5),  # 2.5 days = 2 slots
        ]

        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=4, method="frontload")

        tiny_slots = schedule.get_project_slots(projects[1])
        # Should have 2 slots (int(2.5) = 2)
        assert len(tiny_slots) == 2


class TestSchedulingMethods:
    """Tests for different scheduling methods and edge cases."""

    def test_empty_project_list(self):
        """Test scheduling with no projects."""
        projects = []
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))

        schedule_paced = scheduler.create_schedule(num_weeks=4, method="paced")
        schedule_frontload = scheduler.create_schedule(num_weeks=4, method="frontload")

        # Should create schedules with only empty slots
        assert len(schedule_paced.slots) > 0
        assert len(schedule_frontload.slots) > 0
        assert all(slot.project is None for slot in schedule_paced.slots)
        assert all(slot.project is None for slot in schedule_frontload.slots)

    def test_single_project(self):
        """Test scheduling with a single project."""
        projects = [Project("Solo", date(2024, 12, 31), 10)]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))

        schedule_paced = scheduler.create_schedule(num_weeks=4, method="paced")
        schedule_frontload = scheduler.create_schedule(num_weeks=4, method="frontload")

        # Frontload should assign all 10 slots
        frontload_slots = schedule_frontload.get_project_slots(projects[0])
        assert len(frontload_slots) == 10

        # Paced method respects weekly allocation limits
        # Days until deadline: ~57 days, remaining weeks: ~8.14
        # Ideal days/week: 10 / 8.14 = 1.23, floor = 1 day/week
        # In 4 weeks: 4 days assigned (with accumulation, could be 5)
        paced_slots = schedule_paced.get_project_slots(projects[0])
        assert 4 <= len(paced_slots) <= 6, f"Expected 4-6 slots, got {len(paced_slots)}"

    def test_projects_with_zero_remaining_days(self):
        """Test scheduling with projects that have no remaining work."""
        projects = [
            Project("Done", date(2024, 12, 31), 0),
            Project("Active", date(2024, 12, 31), 5),
        ]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))

        schedule = scheduler.create_schedule(num_weeks=4, method="paced")

        # Done project should have no slots
        done_slots = schedule.get_project_slots(projects[0])
        assert len(done_slots) == 0

        # Active project: 5 days remaining, ~8.14 weeks until deadline
        # Ideal: 5 / 8.14 = 0.61 days/week, floor = 0
        # Will accumulate: 0.61 * 4 = 2.44, so 2 days over 4 weeks
        active_slots = schedule.get_project_slots(projects[1])
        assert 2 <= len(active_slots) <= 4, (
            f"Expected 2-4 slots, got {len(active_slots)}"
        )

    def test_multiple_fractional_day_projects(self):
        """Test scheduling with multiple projects having fractional days."""
        projects = [
            Project("One", date(2024, 12, 31), 1.2),
            Project("Two", date(2024, 12, 31), 2.5),
            Project("Three", date(2024, 12, 31), 3.8),
        ]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))

        schedule = scheduler.create_schedule(num_weeks=4, method="paced")

        # With paced method and weekly limits, projects get allocated based on ideal days/week
        # One: 1.2 / 8.14 = 0.15 days/week, floor=0, accumulates slowly
        # Two: 2.5 / 8.14 = 0.31 days/week, floor=0, accumulates
        # Three: 3.8 / 8.14 = 0.47 days/week, floor=0, accumulates
        # Over 4 weeks, accumulation allows some allocations
        one_slots = len(schedule.get_project_slots(projects[0]))
        two_slots = len(schedule.get_project_slots(projects[1]))
        three_slots = len(schedule.get_project_slots(projects[2]))

        # Verify at least some work gets scheduled
        assert one_slots >= 0
        assert two_slots >= 1
        assert three_slots >= 1
        # Total should be reasonable for 4 weeks (20 slots available)
        total = one_slots + two_slots + three_slots
        assert total <= 20

    def test_frontload_concentrates_work(self):
        """Test that frontload method concentrates work on each project."""
        projects = [
            Project("First", date(2024, 12, 31), 5),
            Project("Second", date(2024, 12, 31), 5),
            Project("Third", date(2024, 12, 31), 5),
        ]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))

        schedule = scheduler.create_schedule(num_weeks=8, method="frontload")

        # Get slots for each project sorted by date
        first_slots = sorted(
            schedule.get_project_slots(projects[0]), key=lambda s: s.date
        )
        second_slots = sorted(
            schedule.get_project_slots(projects[1]), key=lambda s: s.date
        )
        third_slots = sorted(
            schedule.get_project_slots(projects[2]), key=lambda s: s.date
        )

        # First project should end before second project starts
        if first_slots and second_slots:
            last_first = first_slots[-1].date
            first_second = second_slots[0].date
            assert last_first <= first_second, (
                "Frontload should finish First before starting Second"
            )

        # Second project should end before third project starts
        if second_slots and third_slots:
            last_second = second_slots[-1].date
            first_third = third_slots[0].date
            assert last_second <= first_third, (
                "Frontload should finish Second before starting Third"
            )

    def test_paced_method_distributes_work(self):
        """Test that paced method distributes work across the schedule."""
        projects = [
            Project("A", date(2024, 12, 31), 10),
            Project("B", date(2024, 12, 31), 10),
        ]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))

        schedule = scheduler.create_schedule(num_weeks=8, method="paced")

        # Get slots for each project sorted by date
        a_slots = sorted(schedule.get_project_slots(projects[0]), key=lambda s: s.date)
        b_slots = sorted(schedule.get_project_slots(projects[1]), key=lambda s: s.date)

        # Both projects should have work spread across the schedule
        # Check that both projects start early (not frontloaded)
        assert len(a_slots) > 0 and len(b_slots) > 0

        # Both should start in the first week
        first_week_end = date(2024, 11, 10)
        a_starts_early = any(slot.date <= first_week_end for slot in a_slots)
        b_starts_early = any(slot.date <= first_week_end for slot in b_slots)

        assert a_starts_early and b_starts_early, (
            "Paced method should start both projects early"
        )

    def test_invalid_scheduling_method(self):
        """Test that invalid scheduling method raises error."""
        projects = [Project("Test", date(2024, 12, 31), 5)]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))

        try:
            scheduler.create_schedule(num_weeks=4, method="invalid")
            assert False, "Should raise ValueError for invalid method"
        except ValueError as e:
            assert "invalid" in str(e).lower()

    def test_all_same_remaining_days(self):
        """Test scheduling when all projects have the same remaining days."""
        projects = [
            Project("A", date(2024, 12, 31), 5),
            Project("B", date(2024, 12, 31), 5),
            Project("C", date(2024, 12, 31), 5),
        ]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))

        schedule_paced = scheduler.create_schedule(num_weeks=8, method="paced")
        schedule_frontload = scheduler.create_schedule(num_weeks=8, method="frontload")

        # All projects should get equal slots in both methods
        for schedule in [schedule_paced, schedule_frontload]:
            a_slots = len(schedule.get_project_slots(projects[0]))
            b_slots = len(schedule.get_project_slots(projects[1]))
            c_slots = len(schedule.get_project_slots(projects[2]))

            # All should have 5 slots (5 days * 1 slot)
            assert a_slots == 5
            assert b_slots == 5
            assert c_slots == 5

    def test_too_much_work_for_schedule(self):
        """Test scheduling when there's more work than available slots."""
        projects = [
            Project("Huge", date(2024, 12, 31), 100),  # 100 days = 100 slots
        ]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))

        # Only 4 weeks = 20 weekdays = 20 slots
        schedule = scheduler.create_schedule(num_weeks=4, method="paced")

        # Should only assign 20 slots (all available)
        huge_slots = schedule.get_project_slots(projects[0])
        assert len(huge_slots) == 20

        # Statistics should show not fully scheduled
        stats = scheduler.get_statistics(schedule)
        assert not stats[0].fully_scheduled


class TestProjectRenewal:
    """Tests for project renewal functionality."""

    def test_project_with_renewal_days(self):
        """Test creating a project with renewal_days."""
        project = Project(
            name="Renewable",
            end_date=date(2024, 12, 31),
            remaining_days=10,
            renewal_days=5,
        )
        assert project.renewal_days == 5
        assert not project.is_renewal
        assert project.parent_name is None

    def test_renewal_project_generation(self):
        """Test that renewal projects are generated correctly."""
        base_project = Project(
            name="Base",
            end_date=date(2024, 11, 30),
            remaining_days=5,
            start_date=date(2024, 11, 1),
            renewal_days=3,
        )

        scheduler = Scheduler([base_project], start_date=date(2024, 11, 1))
        schedule = scheduler.create_schedule(num_weeks=52, method="paced")

        # Check that renewal project was created
        renewal_projects = [p for p in scheduler.projects if p.is_renewal]
        assert len(renewal_projects) == 1

        renewal = renewal_projects[0]
        assert renewal.name == "Base (Renewal)"
        assert renewal.remaining_days == 3
        assert renewal.parent_name == "Base"
        assert renewal.start_date == date(2024, 12, 1)  # Day after base ends
        assert renewal.end_date == date(2024, 11, 30) + timedelta(days=365)  # One year from parent end_date

    def test_no_renewal_if_outside_horizon(self):
        """Test that renewals aren't created if they start after the planning horizon."""
        base_project = Project(
            name="Late",
            end_date=date(2025, 12, 31),  # Far in future
            remaining_days=5,
            renewal_days=3,
        )

        scheduler = Scheduler([base_project], start_date=date(2024, 11, 1))
        schedule = scheduler.create_schedule(
            num_weeks=4, method="paced"
        )  # Short horizon

        # Renewal should not be created
        renewal_projects = [p for p in scheduler.projects if p.is_renewal]
        # This depends on whether the base project completes within horizon
        # For this test, the renewal start would be after the 4-week horizon

    def test_renewal_project_scheduling(self):
        """Test that renewal projects are scheduled correctly."""
        base_project = Project(
            name="Quick",
            end_date=date(2024, 11, 15),
            remaining_days=1,
            start_date=date(2024, 11, 1),
            renewal_days=2,
        )

        scheduler = Scheduler([base_project], start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=52, method="paced")

        # Check that both base and renewal got scheduled
        base_slots = [
            s for s in schedule.slots if s.project and s.project.name == "Quick"
        ]
        renewal_slots = [
            s
            for s in schedule.slots
            if s.project and s.project.name == "Quick (Renewal)"
        ]

        assert len(base_slots) >= 1  # 1 day = 1 slot
        assert len(renewal_slots) >= 2  # 2 days = 2 slots

    def test_multiple_projects_with_renewals(self):
        """Test scheduling multiple projects with different renewal configurations."""
        projects = [
            Project("A", date(2024, 11, 30), 2, renewal_days=1),
            Project("B", date(2024, 12, 15), 3, renewal_days=2),
            Project("C", date(2024, 12, 31), 4, renewal_days=None),  # No renewal
        ]

        scheduler = Scheduler(projects, start_date=date(2024, 11, 1))
        schedule = scheduler.create_schedule(num_weeks=52, method="paced")

        # Check renewals were created for A and B but not C
        renewal_count = sum(1 for p in scheduler.projects if p.is_renewal)
        assert renewal_count == 2  # A and B should have renewals


class TestYearsLeft:
    """Multi-year grants: ``years_left`` renewal years, discounted for salary."""

    def test_default_years_left_means_no_renewal(self):
        project = Project("Solo", date(2026, 12, 31), 10)
        assert project.years_left == 1
        assert project.renewal_years == 0

        scheduler = Scheduler([project], start_date=date(2026, 1, 1))
        scheduler.create_schedule(num_weeks=208, method="paced")
        assert not [p for p in scheduler.projects if p.is_renewal]

    def test_years_left_generates_one_renewal_per_remaining_year(self):
        """years_left counts the current year, so 5 years is 4 renewals."""
        project = Project("CISNET", date(2026, 12, 31), 40, years_left=5)

        scheduler = Scheduler([project], start_date=date(2026, 1, 1))
        scheduler.create_schedule(num_weeks=520, method="paced")

        renewals = [p for p in scheduler.projects if p.is_renewal]
        assert [p.name for p in renewals] == [
            "CISNET (Renewal)",
            "CISNET (Renewal 2)",
            "CISNET (Renewal 3)",
            "CISNET (Renewal 4)",
        ]
        assert all(p.parent_name == "CISNET" for p in renewals)

    def test_renewal_years_chain_back_to_back(self):
        project = Project("Chain", date(2026, 6, 30), 20, years_left=3)

        scheduler = Scheduler([project], start_date=date(2026, 1, 1))
        scheduler.create_schedule(num_weeks=520, method="paced")

        renewals = sorted(
            (p for p in scheduler.projects if p.is_renewal), key=lambda p: p.start_date
        )
        assert renewals[0].start_date == date(2026, 7, 1)
        assert renewals[0].end_date == date(2026, 6, 30) + timedelta(days=365)
        assert renewals[1].start_date == renewals[0].end_date + timedelta(days=1)
        assert renewals[1].end_date == renewals[0].end_date + timedelta(days=365)

    def test_salary_growth_discounts_each_renewal_year(self):
        """No renewal_days: the current year is the baseline, discounted yearly."""
        project = Project("Grant", date(2026, 12, 31), 100, years_left=3)
        scheduler = Scheduler(
            [project], start_date=date(2026, 1, 1), annual_salary_growth=0.04
        )
        scheduler.create_schedule(num_weeks=520, method="paced")

        renewals = sorted(
            (p for p in scheduler.projects if p.is_renewal), key=lambda p: p.start_date
        )
        assert renewals[0].remaining_days == pytest.approx(100 / 1.04)
        assert renewals[1].remaining_days == pytest.approx(100 / 1.04**2)

    def test_renewal_days_sets_the_first_year_then_discounts(self):
        """An explicit renewal_days is taken as-is; later years shrink from it."""
        project = Project(
            "Grant", date(2026, 12, 31), 100, renewal_days=38, years_left=3
        )
        scheduler = Scheduler(
            [project], start_date=date(2026, 1, 1), annual_salary_growth=0.04
        )
        scheduler.create_schedule(num_weeks=520, method="paced")

        renewals = sorted(
            (p for p in scheduler.projects if p.is_renewal), key=lambda p: p.start_date
        )
        assert renewals[0].remaining_days == pytest.approx(38)
        assert renewals[1].remaining_days == pytest.approx(38 / 1.04)

    def test_zero_growth_keeps_every_year_equal(self):
        project = Project("Flat", date(2026, 12, 31), 30, years_left=4)
        scheduler = Scheduler(
            [project], start_date=date(2026, 1, 1), annual_salary_growth=0.0
        )
        scheduler.create_schedule(num_weeks=520, method="paced")

        renewals = [p for p in scheduler.projects if p.is_renewal]
        assert len(renewals) == 3
        assert all(p.remaining_days == pytest.approx(30) for p in renewals)

    def test_years_beyond_the_horizon_are_not_created(self):
        """A long grant on a short horizon only materializes the years it reaches."""
        project = Project("Long", date(2026, 12, 31), 40, years_left=5)

        scheduler = Scheduler([project], start_date=date(2026, 1, 1))
        scheduler.create_schedule(num_weeks=104, method="paced")

        renewals = [p for p in scheduler.projects if p.is_renewal]
        assert len(renewals) == 1  # Only the year starting 2027-01-01 fits

    def test_renewals_do_not_renew_again(self):
        project = Project("Deep", date(2026, 12, 31), 10, years_left=3)

        scheduler = Scheduler([project], start_date=date(2026, 1, 1))
        scheduler.create_schedule(num_weeks=520, method="paced")

        renewals = [p for p in scheduler.projects if p.is_renewal]
        assert len(renewals) == 2
        assert all(p.renewal_years == 0 for p in renewals)

    def test_renewal_lag_applies_to_every_year(self):
        project = Project(
            "Lagged", date(2026, 6, 30), 10, years_left=3, renewal_lag_days=30
        )

        scheduler = Scheduler([project], start_date=date(2026, 1, 1))
        scheduler.create_schedule(num_weeks=520, method="paced")

        renewals = sorted(
            (p for p in scheduler.projects if p.is_renewal), key=lambda p: p.start_date
        )
        assert renewals[0].start_date == date(2026, 6, 30) + timedelta(days=31)
        assert renewals[1].start_date == renewals[0].end_date + timedelta(days=31)

    def test_total_days_grows_with_years_left(self):
        """The point of years_left: a long horizon shows the full multi-year load."""
        one_year = Project("P", date(2026, 12, 31), 40)
        five_years = Project("P", date(2026, 12, 31), 40, years_left=5)

        totals = []
        for project in (one_year, five_years):
            scheduler = Scheduler([project], start_date=date(2026, 1, 1))
            scheduler.create_schedule(num_weeks=520, method="paced")
            totals.append(sum(p.remaining_days for p in scheduler.projects))

        assert totals[0] == 40
        assert totals[1] > 40 * 4  # Four discounted renewal years on top

    def test_negative_growth_is_rejected(self):
        with pytest.raises(ValueError):
            Scheduler([Project("P", date(2026, 12, 31), 10)], annual_salary_growth=-1)

    def test_years_left_works_with_frontload(self):
        project = Project("F", date(2026, 3, 31), 5, years_left=3)

        scheduler = Scheduler([project], start_date=date(2026, 1, 1))
        schedule = scheduler.create_schedule(num_weeks=520, method="frontload")

        scheduled = {
            s.project.name for s in schedule.slots if s.project is not None
        }
        assert "F (Renewal)" in scheduled
        assert "F (Renewal 2)" in scheduled


class TestEDDPrioritization:
    """Tests for Earliest Due Date (EDD) prioritization."""

    def test_edd_priority_in_paced_method(self):
        """Test that paced method prioritizes projects with earlier deadlines."""
        projects = [
            Project("Late", date(2024, 12, 31), 10),
            Project("Early", date(2024, 11, 15), 10),
            Project("Middle", date(2024, 12, 15), 10),
        ]

        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=12, method="paced")

        # Get first few slots for each project to see which starts earlier
        early_slots = schedule.get_project_slots(projects[1])  # Early deadline
        late_slots = schedule.get_project_slots(projects[0])  # Late deadline

        # Early deadline project should start first or have similar start
        if early_slots and late_slots:
            first_early = min(s.date for s in early_slots)
            first_late = min(s.date for s in late_slots)
            # Early should start at same time or before Late
            assert first_early <= first_late

    def test_edd_priority_in_frontload_method(self):
        """Test that frontload method processes projects in EDD order."""
        projects = [
            Project("Late", date(2024, 12, 31), 5),
            Project("Early", date(2024, 11, 15), 5),
            Project("Middle", date(2024, 12, 15), 5),
        ]

        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=12, method="frontload")

        # Get slots for each project
        early_slots = sorted(
            schedule.get_project_slots(projects[1]), key=lambda s: s.date
        )
        middle_slots = sorted(
            schedule.get_project_slots(projects[2]), key=lambda s: s.date
        )
        late_slots = sorted(
            schedule.get_project_slots(projects[0]), key=lambda s: s.date
        )

        # In frontload with EDD, Early should complete before Middle, Middle before Late
        if early_slots and middle_slots:
            last_early = early_slots[-1].date
            first_middle = middle_slots[0].date
            assert last_early <= first_middle

        if middle_slots and late_slots:
            last_middle = middle_slots[-1].date
            first_late = late_slots[0].date
            assert last_middle <= first_late

    def test_edd_with_same_deadline(self):
        """Test scheduling when projects have the same deadline."""
        projects = [
            Project("Big", date(2024, 12, 31), 10),
            Project("Small", date(2024, 12, 31), 2),
        ]

        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=8, method="frontload")

        # With same deadline, should prioritize by remaining work (descending)
        big_slots = schedule.get_project_slots(projects[0])
        small_slots = schedule.get_project_slots(projects[1])

        # Both should get scheduled
        assert len(big_slots) == 10  # 10 days * 1 slot
        assert len(small_slots) == 2  # 2 days * 1 slot


class TestDefaultWeeks:
    """Tests for default planning horizon of 52 weeks."""

    def test_default_weeks_is_52(self):
        """Test that default planning horizon is 52 weeks."""
        projects = [Project("Test", date(2025, 12, 31), 50)]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))

        # Call without specifying num_weeks
        schedule = scheduler.create_schedule()

        # Should span approximately 52 weeks
        weeks = (schedule.end_date - schedule.start_date).days / 7
        assert abs(weeks - 52) < 1  # Allow small rounding difference

    def test_52_week_schedule_capacity(self):
        """Test that 52-week schedule has correct capacity."""
        projects = []
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=52)

        # Count unique working days (Mon-Fri only)
        unique_dates = set(s.date for s in schedule.slots if s.date.weekday() < 5)
        working_days = len(unique_dates)

        # 52 weeks ≈ 260 working days (52 * 5)
        expected_working_days = 52 * 5
        # Allow some variance due to start day
        assert abs(working_days - expected_working_days) < 5


# class TestEnhancedVisualization:
#     """Tests for enhanced tile visualization."""

#     def test_visualization_shows_renewal_indicator(self):
#         """Test that legend shows renewal projects with indicator."""
#         base_project = Project("Base", date(2024, 11, 30), 2, renewal_days=1)
#         scheduler = Scheduler([base_project], start_date=date(2024, 11, 4))
#         schedule = scheduler.create_schedule(num_weeks=8, method="paced")

#         output = render_tiles(schedule, show_legend=True)

#         # Should show renewal in legend
#         assert "(Renewal)" in output or "Renewal" in output

#     def test_calendar_grid_rendering(self):
#         """Test that calendar grid renders without errors."""
#         projects = [
#             Project("A", date(2024, 12, 31), 10),
#             Project("B", date(2024, 12, 15), 5),
#         ]
#         scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
#         schedule = scheduler.create_schedule(num_weeks=12, method="paced")

#         output = render_tiles(schedule, show_legend=True)

#         # Should contain day names (Mon, Wed, Fri only in new visualization)
#         assert "Mon" in output
#         assert "Wed" in output
#         assert "Fri" in output

#         # Should contain legend
#         assert "Legend" in output


class TestImportFunctionality:
    """Tests for Excel import functionality."""

    def test_import_config_defaults(self):
        """Test loading default import configuration."""
        from planner.importer import DEFAULT_IMPORT_CONFIG, load_import_config

        config = load_import_config("nonexistent_config.json")

        # Should return defaults
        assert config["sheet_name"] == DEFAULT_IMPORT_CONFIG["sheet_name"]
        assert "column_mapping" in config
        assert "name" in config["column_mapping"]

    def test_save_import_config(self, tmp_path):
        """Test saving import configuration."""
        from planner.importer import save_default_import_config

        config_file = tmp_path / "test_import_config.json"
        save_default_import_config(str(config_file))

        # Should create file
        assert config_file.exists()

        # Should be valid JSON
        with open(config_file) as f:
            config = json.load(f)

        assert "column_mapping" in config
        assert "sheet_name" in config

    def test_update_projects_json_new_projects(self, tmp_path):
        """Test adding new projects to projects.json."""
        from planner.importer import update_projects_json

        projects_file = tmp_path / "projects.json"

        new_projects = [
            {"name": "New A", "end_date": "2024-12-31", "remaining_days": 10},
            {"name": "New B", "end_date": "2024-11-30", "remaining_days": 5},
        ]

        stats = update_projects_json(new_projects, str(projects_file))

        assert stats["added"] == 2
        assert stats["updated"] == 0
        assert stats["unchanged"] == 0

        # Verify file was created
        assert projects_file.exists()

        with open(projects_file) as f:
            data = json.load(f)

        assert len(data["projects"]) == 2

    def test_update_projects_json_update_existing(self, tmp_path):
        """Test updating existing projects in projects.json."""
        from planner.importer import update_projects_json

        projects_file = tmp_path / "projects.json"

        # Create initial file
        initial_data = {
            "projects": [
                {"name": "Existing", "end_date": "2024-12-31", "remaining_days": 10}
            ]
        }
        with open(projects_file, "w") as f:
            json.dump(initial_data, f)

        # Update with new remaining_days
        new_projects = [
            {"name": "Existing", "end_date": "2024-12-31", "remaining_days": 15}
        ]

        stats = update_projects_json(new_projects, str(projects_file))

        assert stats["added"] == 0
        assert stats["updated"] == 1
        assert stats["unchanged"] == 0

        # Verify update
        with open(projects_file) as f:
            data = json.load(f)

        assert data["projects"][0]["remaining_days"] == 15

    def test_update_projects_json_mixed_operations(self, tmp_path):
        """Test mixed add/update/unchanged operations."""
        from planner.importer import update_projects_json

        projects_file = tmp_path / "projects.json"

        # Create initial file
        initial_data = {
            "projects": [
                {"name": "Existing", "end_date": "2024-12-31", "remaining_days": 10},
                {"name": "Unchanged", "end_date": "2024-11-30", "remaining_days": 5},
            ]
        }
        with open(projects_file, "w") as f:
            json.dump(initial_data, f)

        # Mixed operations
        new_projects = [
            {
                "name": "Existing",
                "end_date": "2024-12-31",
                "remaining_days": 15,
            },  # Update
            {
                "name": "Unchanged",
                "end_date": "2024-11-30",
                "remaining_days": 5,
            },  # Unchanged
            {"name": "New", "end_date": "2024-10-31", "remaining_days": 3},  # Add
        ]

        stats = update_projects_json(new_projects, str(projects_file))

        assert stats["added"] == 1
        assert stats["updated"] == 1
        assert stats["unchanged"] == 1


class TestEdgeCases:
    """Tests for edge cases with new features."""

    def test_project_with_start_date_in_future(self):
        """Test project with start_date in the future."""
        future_project = Project(
            name="Future",
            start_date=date(2024, 12, 1),
            end_date=date(2024, 12, 31),
            remaining_days=5,
        )

        # Should still be schedulable
        scheduler = Scheduler([future_project], start_date=date(2024, 11, 1))
        schedule = scheduler.create_schedule(num_weeks=12, method="paced")

        # Project should get scheduled
        slots = schedule.get_project_slots(future_project)
        assert len(slots) > 0

    def test_renewal_with_zero_days(self):
        """Test project with renewal_days=0."""
        project = Project(
            name="NoRenewal",
            end_date=date(2024, 11, 30),
            remaining_days=2,
            renewal_days=0,
        )

        scheduler = Scheduler([project], start_date=date(2024, 11, 1))
        schedule = scheduler.create_schedule(num_weeks=8, method="paced")

        # Should not create renewal
        renewals = [p for p in scheduler.projects if p.is_renewal]
        assert len(renewals) == 0

    def test_very_long_planning_horizon(self):
        """Test with very long planning horizon (104 weeks = 2 years)."""
        projects = [Project("Long", date(2026, 12, 31), 100)]

        scheduler = Scheduler(projects, start_date=date(2024, 11, 1))
        schedule = scheduler.create_schedule(num_weeks=104, method="paced")

        # Should create schedule without errors
        assert len(schedule.slots) > 0
        weeks = (schedule.end_date - schedule.start_date).days / 7
        assert abs(weeks - 104) < 1


class TestWeeklyAllocationLimits:
    """Tests for weekly allocation limits in paced method."""

    def test_weekly_allocation_respects_limits(self):
        """Test that projects don't exceed their weekly allocation limits."""
        projects = [
            Project("A", date(2024, 12, 31), 10),
            Project("B", date(2024, 12, 31), 10),
            Project("C", date(2024, 12, 31), 10),
        ]

        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=12, method="paced")

        # Check that each project respects weekly allocation limits
        for project in projects:
            project_slots = schedule.get_project_slots(project)

            # Group slots by week
            weeks = {}
            for slot in project_slots:
                week_start = slot.date - timedelta(days=slot.date.weekday())
                if week_start not in weeks:
                    weeks[week_start] = 0
                weeks[week_start] += 1

            # Calculate expected max days per week
            # Days until deadline: ~57 days, remaining weeks: ~8.14
            # Ideal days/week: 10 / 8.14 = 1.23, floor = 1 day/week
            # With accumulation, could be 2 some weeks
            for week, count in weeks.items():
                assert count <= 3, (
                    f"Project {project.name} exceeded weekly limit in week {week}: {count} days"
                )

    def test_weekly_allocation_with_large_project(self):
        """Test weekly allocation limits with unequal project sizes."""
        projects = [
            Project("Large", date(2024, 12, 31), 30),
            Project("Small", date(2024, 12, 31), 5),
        ]

        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=12, method="paced")

        # Check weekly allocations for large project
        large_slots = schedule.get_project_slots(projects[0])
        weeks = {}
        for slot in large_slots:
            week_start = slot.date - timedelta(days=slot.date.weekday())
            if week_start not in weeks:
                weeks[week_start] = 0
            weeks[week_start] += 1

        # Large project: 30 days, ~8.14 weeks
        # Ideal: 30 / 8.14 = 3.68 days/week, floor = 3 days/week
        # Should not exceed 5 days/week even with accumulation
        for week, count in weeks.items():
            assert count <= 5, (
                f"Large project exceeded reasonable weekly limit in week {week}: {count} days"
            )

    def test_continuity_with_multiple_projects(self):
        """Test continuity with multiple projects ensures fair distribution."""
        projects = [
            Project("A", date(2024, 12, 31), 15),
            Project("B", date(2024, 12, 15), 15),
            Project("C", date(2024, 11, 30), 15),
        ]

        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=12, method="paced")

        # All projects should get scheduled
        for project in projects:
            slots = schedule.get_project_slots(project)
            assert len(slots) > 0, f"{project.name} should get scheduled"

        # Check that work is distributed across the schedule (not all at start)
        for project in projects:
            project_slots = schedule.get_project_slots(project)
            if project_slots:
                dates = sorted(set(s.date for s in project_slots))
                # Should span multiple weeks
                date_range = (dates[-1] - dates[0]).days
                # With continuity, should still span some time (not all in one week)
                if len(project_slots) > 10:  # Projects with more than 5 days
                    assert date_range > 7, (
                        f"{project.name} should span more than a week"
                    )

    def test_continuity_resets_on_weekends(self):
        """Test that continuity is reset on weekends."""
        projects = [Project("A", date(2024, 12, 31), 20)]

        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))  # Monday
        schedule = scheduler.create_schedule(num_weeks=4, method="paced")

        # Get slots and check that there are no weekend slots
        a_slots = schedule.get_project_slots(projects[0])

        for slot in a_slots:
            assert slot.date.weekday() < 5, "No work should be scheduled on weekends"

        # Weekend should act as natural break in continuity
        # This is implicitly tested by the algorithm


class TestPacedSchedulePacing:
    def test_long_project_finishes_near_deadline(self):
        """A long, low-budget project should not be consumed months early."""
        imabc = Project(
            name="IMABC",
            start_date=date(2026, 2, 1),
            end_date=date(2027, 2, 1),
            remaining_days=26,
            priority=1,
        )

        scheduler = Scheduler([imabc], start_date=date(2026, 1, 26))
        schedule = scheduler.create_schedule(num_weeks=104, method="paced")

        slots = schedule.get_project_slots(imabc)
        assert len(slots) == 26

        last_date = max(s.date for s in slots)
        assert last_date <= imabc.end_date
        assert last_date >= imabc.end_date - timedelta(weeks=8)


# class TestAvailabilityPlot:
#     """Tests for availability plotting functionality."""

#     def test_compute_weekly_availability_empty_schedule(self):
#         """Test availability computation with an empty schedule."""
#         schedule = Schedule(slots=[], start_date=date(2024, 1, 1))
#         availability = compute_weekly_availability(schedule, num_weeks=4)

#         assert len(availability) == 4
#         # All weeks should be 100% available (no scheduled work)
#         for week in availability:
#             assert week.percent_available == 100.0
#             assert week.total_slots == 5  # 5 weekdays * 1 slot

#     def test_compute_weekly_availability_fully_scheduled(self):
#         """Test availability with a fully scheduled week."""
#         start = date(2024, 1, 1)  # Monday
#         schedule = Schedule(start_date=start, end_date=start + timedelta(weeks=1))

#         # Create a project and schedule all slots in first week
#         project = Project("Full Week", date(2024, 12, 31), 5)

#         # Add 5 weekdays * 1 slot = 5 slots
#         for day in range(5):
#             current_date = start + timedelta(days=day)
#             schedule.slots.append(ScheduledSlot(current_date, project))

#         availability = compute_weekly_availability(schedule, num_weeks=2)

#         assert len(availability) == 2
#         # First week should be 0% available (fully scheduled)
#         assert availability[0].percent_available == 0.0
#         assert availability[0].total_slots == 5
#         assert availability[0].unscheduled_slots == 0

#         # Second week should be 100% available (no slots)
#         assert availability[1].percent_available == 100.0

#     def test_compute_weekly_availability_partial(self):
#         """Test availability with partially scheduled weeks."""
#         start = date(2024, 1, 1)  # Monday
#         schedule = Schedule(start_date=start)

#         project = Project("Partial", date(2024, 12, 31), 2)

#         # Schedule 2 slots out of 5 in first week (40%)
#         for day in range(2):
#             current_date = start + timedelta(days=day)
#             schedule.slots.append(ScheduledSlot(current_date, project))

#         availability = compute_weekly_availability(schedule, num_weeks=1)

#         assert len(availability) == 1
#         # Should have 2 scheduled, 3 unscheduled (60% available)
#         assert availability[0].total_slots == 5
#         assert availability[0].unscheduled_slots == 3
#         assert availability[0].percent_available == 60.0

#     def test_compute_weekly_availability_with_unassigned_slots(self):
#         """Test availability computation with explicit unassigned slots."""
#         start = date(2024, 1, 1)  # Monday
#         schedule = Schedule(start_date=start)

#         project = Project("Test", date(2024, 12, 31), 1)

#         # Create mix of assigned and unassigned slots
#         schedule.slots.append(ScheduledSlot(start, project))  # Assigned day 1
#         schedule.slots.append(ScheduledSlot(start + timedelta(days=1), None))  # Unassigned day 2

#         availability = compute_weekly_availability(schedule, num_weeks=1)

#         assert availability[0].total_slots == 5
#         assert availability[0].unscheduled_slots == 4  # 1 assigned, 4 unassigned
#         assert availability[0].percent_available == 80.0

#     def test_availability_increases_over_time(self):
#         """Test that availability increases as projects complete."""
#         start = date(2024, 1, 1)  # Monday
#         projects = [
#             Project("Short", date(2024, 2, 1), 3),   # 3 slots
#             Project("Medium", date(2024, 3, 1), 5),  # 5 slots
#         ]

#         scheduler = Scheduler(projects, start_date=start)
#         schedule = scheduler.create_schedule(num_weeks=8, method="frontload")

#         availability = compute_weekly_availability(schedule, num_weeks=8)

#         # Availability should generally increase over time
#         # as projects complete
#         early_avg = sum(w.percent_available for w in availability[:2]) / 2
#         late_avg = sum(w.percent_available for w in availability[-2:]) / 2

#         assert late_avg > early_avg, "Availability should increase as projects complete"

#     def test_render_availability_plot_basic(self):
#         """Test basic rendering of availability plot."""
#         start = date(2024, 1, 1)
#         schedule_paced = Schedule(start_date=start)
#         schedule_frontload = Schedule(start_date=start)

#         paced_avail = compute_weekly_availability(schedule_paced, num_weeks=4)
#         frontload_avail = compute_weekly_availability(schedule_frontload, num_weeks=4)

#         plot = render_availability_plot(paced_avail, frontload_avail)

#         # Check that plot contains expected elements
#         assert "AVAILABILITY OVER TIME" in plot
#         assert "Legend:" in plot
#         assert "Paced" in plot or "P" in plot
#         assert "Frontload" in plot or "F" in plot
#         assert "%" in plot  # Should have percentage markers

#     def test_render_availability_plot_empty(self):
#         """Test plotting with no data."""
#         plot = render_availability_plot([], [])
#         assert "No availability data" in plot

#     def test_availability_plot_width_and_height(self):
#         """Test that plot respects width and height parameters."""
#         start = date(2024, 1, 1)
#         schedule = Schedule(start_date=start)
#         avail = compute_weekly_availability(schedule, num_weeks=4)

#         plot = render_availability_plot(avail, avail, plot_width=50, plot_height=10)

#         lines = plot.split('\n')
#         # Find the plot lines (between top and bottom borders)
#         plot_lines = [l for l in lines if '│' in l and '─' in l]

#         # Should have border lines
#         assert len(plot_lines) > 0

#     def test_weekly_availability_week_numbers(self):
#         """Test that week numbers are correctly assigned."""
#         start = date(2024, 1, 1)
#         schedule = Schedule(start_date=start)

#         availability = compute_weekly_availability(schedule, num_weeks=5)

#         assert len(availability) == 5
#         for i, week in enumerate(availability):
#             assert week.week_number == i
#             expected_start = start + timedelta(weeks=i)
#             assert week.start_date == expected_start

#     def test_availability_comparison_paced_vs_frontload(self):
#         """Test that paced and frontload methods show different availability patterns."""
#         start = date(2024, 1, 1)
#         projects = [
#             Project("A", date(2024, 3, 1), 10),
#             Project("B", date(2024, 4, 1), 10),
#         ]

#         scheduler = Scheduler(projects, start_date=start)
#         schedule_paced = scheduler.create_schedule(num_weeks=12, method="paced")
#         schedule_frontload = scheduler.create_schedule(num_weeks=12, method="frontload")

#         paced_avail = compute_weekly_availability(schedule_paced, num_weeks=12)
#         frontload_avail = compute_weekly_availability(schedule_frontload, num_weeks=12)

#         # Both should have same number of weeks
#         assert len(paced_avail) == len(frontload_avail) == 12

#         # Frontload should show lower availability early and higher later
#         # (work is concentrated at the beginning)
#         frontload_early = frontload_avail[0].percent_available
#         frontload_late = frontload_avail[-1].percent_available

#         # Later weeks should have more availability in frontload
#         assert frontload_late >= frontload_early


class TestProbabilityFiltering:
    """Tests for probability-based project filtering."""

    def test_project_creation_with_probability(self):
        """Test that Project can be created with probability field."""
        project = Project(
            name="Test Project",
            end_date=date(2024, 12, 31),
            remaining_days=10,
            probability=0.8,
        )
        assert project.probability == 0.8

    def test_project_default_probability(self):
        """Test that Project defaults to probability 1.0."""
        project = Project(
            name="Test Project",
            end_date=date(2024, 12, 31),
            remaining_days=10,
        )
        assert project.probability == 1.0

    def test_filter_projects_by_probability_basic(self):
        """Test basic filtering by probability threshold."""
        from planner.analysis import filter_projects_by_probability

        projects = [
            Project("Active", date(2024, 12, 31), 10, probability=1.0),
            Project("Likely", date(2024, 12, 31), 10, probability=0.9),
            Project("Maybe", date(2024, 12, 31), 10, probability=0.5),
            Project("Unlikely", date(2024, 12, 31), 10, probability=0.2),
        ]

        # Filter at 0.8 threshold
        filtered = filter_projects_by_probability(projects, 0.8)
        assert len(filtered) == 2
        assert filtered[0].name == "Active"
        assert filtered[1].name == "Likely"

    def test_filter_projects_by_probability_threshold_zero(self):
        """Test filtering with threshold of 0 includes all projects."""
        from planner.analysis import filter_projects_by_probability

        projects = [
            Project("A", date(2024, 12, 31), 10, probability=1.0),
            Project("B", date(2024, 12, 31), 10, probability=0.5),
            Project("C", date(2024, 12, 31), 10, probability=0.1),
        ]

        filtered = filter_projects_by_probability(projects, 0.0)
        assert len(filtered) == 3

    def test_filter_projects_by_probability_threshold_one(self):
        """Test filtering with threshold of 1.0 includes only probability=1 projects."""
        from planner.analysis import filter_projects_by_probability

        projects = [
            Project("Active1", date(2024, 12, 31), 10, probability=1.0),
            Project("Active2", date(2024, 12, 31), 10, probability=1.0),
            Project("Likely", date(2024, 12, 31), 10, probability=0.9),
        ]

        filtered = filter_projects_by_probability(projects, 1.0)
        assert len(filtered) == 2
        assert all(p.probability == 1.0 for p in filtered)

    def test_filter_projects_empty_list(self):
        """Test filtering with empty project list."""
        from planner.analysis import filter_projects_by_probability

        filtered = filter_projects_by_probability([], 0.8)
        assert len(filtered) == 0

    def test_load_projects_with_probability(self, tmp_path):
        """Test loading projects from JSON with probability field."""
        from planner.analysis import load_projects

        config = {
            "projects": [
                {
                    "name": "Active Project",
                    "end_date": "2024-12-31",
                    "remaining_days": 10,
                    "probability": 1.0,
                },
                {
                    "name": "Proposal",
                    "end_date": "2024-12-31",
                    "remaining_days": 15,
                    "probability": 0.6,
                },
            ]
        }

        config_file = tmp_path / "test_config.json"
        with open(config_file, "w") as f:
            json.dump(config, f)

        projects = load_projects(str(config_file))
        assert len(projects) == 2
        assert projects[0].probability == 1.0
        assert projects[1].probability == 0.6

    def test_load_projects_without_probability(self, tmp_path):
        """Test loading projects from JSON without probability field defaults to 1.0."""
        from planner.analysis import load_projects

        config = {
            "projects": [
                {
                    "name": "Project A",
                    "end_date": "2024-12-31",
                    "remaining_days": 10,
                }
            ]
        }

        config_file = tmp_path / "test_config.json"
        with open(config_file, "w") as f:
            json.dump(config, f)

        projects = load_projects(str(config_file))
        assert len(projects) == 1
        assert projects[0].probability == 1.0

    def test_load_projects_without_end_date_defaults_to_one_year(self, tmp_path):
        """A missing end_date defaults to one year after start_date."""
        from planner.analysis import load_projects

        config = {
            "projects": [
                {
                    "name": "Missing End Date",
                    "remaining_days": 10,
                    "start_date": "2026-01-01",
                },
                {
                    "name": "Null End Date",
                    "remaining_days": 10,
                    "start_date": "2026-01-01",
                    "end_date": None,
                },
            ]
        }

        config_file = tmp_path / "test_config.json"
        with open(config_file, "w") as f:
            json.dump(config, f)

        projects = load_projects(str(config_file))
        assert len(projects) == 2
        for project in projects:
            assert project.end_date == date(2026, 1, 1) + timedelta(days=365)

    def test_load_projects_without_end_date_or_start_date(self, tmp_path):
        """Without a start_date, the default end_date is one year from today."""
        from planner.analysis import load_projects

        config = {"projects": [{"name": "No Dates", "remaining_days": 10}]}

        config_file = tmp_path / "test_config.json"
        with open(config_file, "w") as f:
            json.dump(config, f)

        projects = load_projects(str(config_file))
        assert projects[0].start_date is None
        assert projects[0].end_date == date.today() + timedelta(days=365)

    def test_scheduler_with_filtered_projects(self):
        """Test that scheduler works correctly with filtered projects."""
        from planner.analysis import filter_projects_by_probability

        projects = [
            Project("High Priority", date(2024, 2, 28), 5, probability=1.0),
            Project("Medium Priority", date(2024, 3, 15), 8, probability=0.9),
            Project("Low Priority", date(2024, 3, 31), 10, probability=0.3),
        ]

        # Filter at 0.8 threshold
        filtered = filter_projects_by_probability(projects, 0.8)
        assert len(filtered) == 2

        # Create schedule with filtered projects
        start = date(2024, 1, 1)
        scheduler = Scheduler(filtered, start_date=start)
        schedule = scheduler.create_schedule(num_weeks=12, method="paced")

        # Verify only filtered projects appear in schedule
        scheduled_projects = {slot.project for slot in schedule.slots if slot.project}
        scheduled_names = {p.name for p in scheduled_projects}

        assert "High Priority" in scheduled_names
        assert "Medium Priority" in scheduled_names
        assert "Low Priority" not in scheduled_names


class TestDayReassignment:
    """Tests for reassigning paced days that cannot be covered."""

    @staticmethod
    def _oversubscribed_projects():
        """Three projects that together demand ~3x the available capacity."""
        start = date(2026, 1, 5)  # Monday
        end = start + timedelta(days=180)
        return [
            Project(f"P{i}", end, 120, start_date=start, priority=i) for i in range(3)
        ]

    def test_disabled_by_default(self):
        """No reassignment happens unless it is asked for."""
        scheduler = Scheduler(self._oversubscribed_projects(), start_date=date(2026, 1, 5))
        with pytest.warns(UserWarning):
            schedule = scheduler.create_schedule(num_weeks=26, method="paced")

        assert schedule.reassignments == []
        assert schedule.total_reassigned_days == 0

    def test_oversubscription_reassigns_exactly_the_infeasible_days(self):
        """Only the days that exceed capacity are handed off -- no more, no less."""
        start = date(2026, 1, 5)
        projects = self._oversubscribed_projects()
        scheduler = Scheduler(projects, start_date=start)
        schedule = scheduler.create_schedule(
            num_weeks=26, method="paced", reassign_days=True
        )

        capacity = scheduler._count_weekdays_inclusive(start, projects[0].end_date)
        demand = sum(p.slots_remaining for p in projects)
        assert schedule.total_reassigned_days == demand - capacity

    def test_lowest_priority_sheds_first(self):
        """The shedding lands on expendable work, not on the top priority."""
        scheduler = Scheduler(self._oversubscribed_projects(), start_date=date(2026, 1, 5))
        schedule = scheduler.create_schedule(
            num_weeks=26, method="paced", reassign_days=True
        )
        by_name = {p.name: p for p in scheduler.projects}

        # P2 has the highest priority, P0 the lowest
        assert schedule.reassigned_days_for(by_name["P2"]) == 0
        assert schedule.reassigned_days_for(by_name["P0"]) > schedule.reassigned_days_for(
            by_name["P1"]
        )

    def test_feasible_schedule_reassigns_nothing(self):
        """A schedule with spare capacity has no days to hand off."""
        start = date(2026, 1, 5)
        projects = [
            Project("Small", start + timedelta(days=180), 20, start_date=start),
        ]
        scheduler = Scheduler(projects, start_date=start)
        schedule = scheduler.create_schedule(
            num_weeks=26, method="paced", reassign_days=True
        )

        assert schedule.total_reassigned_days == 0

    def test_reassigned_days_leave_the_budget(self):
        """Days scheduled plus days reassigned account for the whole budget."""
        scheduler = Scheduler(self._oversubscribed_projects(), start_date=date(2026, 1, 5))
        schedule = scheduler.create_schedule(
            num_weeks=26, method="paced", reassign_days=True
        )

        for project in scheduler.projects:
            scheduled = len(schedule.get_project_slots(project))
            reassigned = schedule.reassigned_days_for(project)
            # Deadlines all fall inside the horizon, so nothing is left over
            assert scheduled + reassigned == project.slots_remaining

    def test_deadline_closes_out_remaining_budget(self):
        """A project cannot end its life with unaccounted budget."""
        start = date(2026, 1, 5)
        # 60 days of work due in a month: most of it has to go to someone else
        crunched = Project("Crunch", start + timedelta(days=30), 60, start_date=start)
        scheduler = Scheduler([crunched], start_date=start)
        schedule = scheduler.create_schedule(
            num_weeks=26, method="paced", reassign_days=True
        )

        closeout = [r for r in schedule.reassignments if r.date == crunched.end_date]
        assert closeout
        assert (
            len(schedule.get_project_slots(crunched))
            + schedule.reassigned_days_for(crunched)
            == crunched.slots_remaining
        )

    def test_reassignment_frees_capacity_for_priority_work(self):
        """Handing off days lets the remaining schedule cover more of the budget."""
        start = date(2026, 1, 5)
        scheduler_off = Scheduler(self._oversubscribed_projects(), start_date=start)
        with pytest.warns(UserWarning):
            baseline = scheduler_off.create_schedule(num_weeks=26, method="paced")

        scheduler_on = Scheduler(self._oversubscribed_projects(), start_date=start)
        with_reassignment = scheduler_on.create_schedule(
            num_weeks=26, method="paced", reassign_days=True
        )

        # Same capacity, but the shortfall is now accounted for rather than dropped
        baseline_missing = sum(
            p.slots_remaining - len(baseline.get_project_slots(p))
            for p in scheduler_off.projects
        )
        remaining_missing = sum(
            p.slots_remaining
            - len(with_reassignment.get_project_slots(p))
            - with_reassignment.reassigned_days_for(p)
            for p in scheduler_on.projects
        )
        assert remaining_missing < baseline_missing

    def test_cadence_controls_checkpoint_count(self):
        """A shorter cadence books reassignments more often."""
        start = date(2026, 1, 5)
        monthly = Scheduler(
            self._oversubscribed_projects(), start_date=start
        ).create_schedule(
            num_weeks=26, method="paced", reassign_days=True,
            reassignment_cadence_days=30,
        )
        weekly = Scheduler(
            self._oversubscribed_projects(), start_date=start
        ).create_schedule(
            num_weeks=26, method="paced", reassign_days=True,
            reassignment_cadence_days=7,
        )

        assert len(weekly.reassignments) > len(monthly.reassignments)
        # Checkpoints land on cadence boundaries counted in calendar days
        for entry in monthly.reassignments:
            assert (entry.date - start).days % 30 == 29

    def test_checkpoint_fires_on_weekend_cadence(self):
        """A cadence landing on a weekend still books its reassignment."""
        start = date(2026, 1, 5)  # Monday; day offset 5 is Saturday Jan 10
        schedule = Scheduler(
            self._oversubscribed_projects(), start_date=start
        ).create_schedule(
            num_weeks=26, method="paced", reassign_days=True,
            reassignment_cadence_days=6,
        )

        weekend_dates = [r.date for r in schedule.reassignments if r.date.weekday() >= 5]
        assert weekend_dates

    def test_frontload_rejects_reassignment(self):
        """Reassignment is a paced-method feature."""
        scheduler = Scheduler(self._oversubscribed_projects(), start_date=date(2026, 1, 5))
        with pytest.raises(ValueError, match="paced"):
            scheduler.create_schedule(
                num_weeks=26, method="frontload", reassign_days=True
            )

    def test_invalid_cadence_rejected(self):
        """A cadence below one day is an error."""
        scheduler = Scheduler(self._oversubscribed_projects(), start_date=date(2026, 1, 5))
        with pytest.raises(ValueError, match="cadence"):
            scheduler.create_schedule(
                num_weeks=26, method="paced", reassign_days=True,
                reassignment_cadence_days=0,
            )

    def test_more_projects_reassign_more_days(self):
        """Selecting extra (pending) projects increases days reassigned out."""
        start = date(2026, 1, 5)
        end = start + timedelta(days=180)
        active = [Project("Active", end, 100, start_date=start)]
        pending = [
            Project(f"Pending {i}", end, 100, start_date=start, probability=0.5)
            for i in range(3)
        ]

        few = Scheduler(list(active), start_date=start).create_schedule(
            num_weeks=26, method="paced", reassign_days=True
        )
        many = Scheduler(active + pending, start_date=start).create_schedule(
            num_weeks=26, method="paced", reassign_days=True
        )

        assert many.total_reassigned_days > few.total_reassigned_days


class TestReassignmentHorizonBoundary:
    """Reassignment has to account for the edge of the planning horizon.

    Every scenario here has deadlines at or beyond the horizon end. Judging only
    projects that expire *inside* the horizon made an oversubscribed plan report
    nothing to reassign, which is what the app showed with all projects selected.
    """

    START = date(2026, 1, 5)  # Monday
    WEEKS = 26

    def _horizon_end(self, weeks=None):
        return self.START + timedelta(days=(weeks or self.WEEKS) * 7 - 1)

    def _solve(self, projects, weeks=None, **kwargs):
        scheduler = Scheduler(projects, start_date=self.START)
        schedule = scheduler.create_schedule(
            num_weeks=weeks or self.WEEKS,
            method="paced",
            reassign_days=True,
            **kwargs,
        )
        return scheduler, schedule

    def test_schedule_end_date_is_the_last_day_covered(self):
        """The horizon ends on the last day iterated, not the day after it.

        Reassignment books its close-outs on real dates, so an end date past the
        last iterated day is unreachable and a deadline there never settles.
        """
        _, schedule = self._solve([Project("P", self._horizon_end(), 10)])
        last_slot = max(s.date for s in schedule.slots)

        assert schedule.end_date == self._horizon_end()
        assert last_slot <= schedule.end_date
        # Every workday up to the end date has a slot
        assert is_workday(schedule.end_date) == (last_slot == schedule.end_date)

    def test_deadline_on_the_horizon_boundary_is_closed_out(self):
        """A deadline landing exactly on the last day still sheds its days.

        Regression: the horizon end used to sit one day past the last iterated
        day, so this project's close-out never fired and the solver spun until it
        hit the iteration cap.
        """
        boundary = self._horizon_end()
        projects = [
            Project(f"P{i}", boundary, 120, start_date=self.START, priority=i)
            for i in range(3)
        ]
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # no non-convergence warning allowed
            scheduler, schedule = self._solve(projects)

        capacity = scheduler._count_weekdays_inclusive(self.START, boundary)
        demand = sum(p.slots_remaining for p in projects)
        assert schedule.total_reassigned_days == demand - capacity

    def test_oversubscription_past_the_horizon_still_reassigns(self):
        """The reported bug: deadlines beyond the horizon reported nothing to shed."""
        projects = [
            Project(
                f"P{i}",
                self.START + timedelta(days=400),
                120,
                start_date=self.START,
                priority=i,
            )
            for i in range(3)
        ]
        scheduler, schedule = self._solve(projects)

        capacity = scheduler._count_weekdays_inclusive(self.START, schedule.end_date)
        due = sum(scheduler._due_by_horizon(p, schedule.end_date) for p in projects)
        assert due > capacity  # the plan really is oversubscribed
        assert schedule.total_reassigned_days > 0

    def test_deadline_one_day_past_the_horizon_is_measured(self):
        """Crossing the boundary must not switch measurement off."""
        inside = [
            Project(f"In{i}", self._horizon_end(), 120, start_date=self.START)
            for i in range(3)
        ]
        outside = [
            Project(
                f"Out{i}",
                self._horizon_end() + timedelta(days=1),
                120,
                start_date=self.START,
            )
            for i in range(3)
        ]

        _, inside_schedule = self._solve(inside)
        _, outside_schedule = self._solve(outside)

        assert outside_schedule.total_reassigned_days > 0
        # One extra day of runway can only reduce the shortfall, and barely
        assert outside_schedule.total_reassigned_days <= (
            inside_schedule.total_reassigned_days
        )
        assert inside_schedule.total_reassigned_days - (
            outside_schedule.total_reassigned_days
        ) <= len(inside)

    def test_feasible_past_the_horizon_reassigns_nothing(self):
        """A project with room to finish after the horizon keeps all of its days."""
        roomy = Project(
            "Roomy", self.START + timedelta(days=400), 30, start_date=self.START
        )
        _, schedule = self._solve([roomy])

        assert schedule.total_reassigned_days == 0

    def test_horizon_end_closes_out_when_no_checkpoint_fires(self):
        """A cadence longer than the horizon still books every quota day."""
        projects = [
            Project(
                f"P{i}",
                self.START + timedelta(days=400),
                120,
                start_date=self.START,
                priority=i,
            )
            for i in range(3)
        ]
        scheduler, schedule = self._solve(projects, reassignment_cadence_days=365)

        assert schedule.total_reassigned_days > 0
        assert {r.date for r in schedule.reassignments} == {schedule.end_date}

    def test_binding_deadlines_make_the_horizon_length_irrelevant(self):
        """When the deadline binds, extending the horizon changes nothing.

        Past-horizon projects are judged on their paced share of the window, so a
        longer horizon claims more of their budget. Projects that expire inside
        every horizon tried must be immune to that.
        """
        def projects():
            return [
                Project(
                    f"P{i}",
                    self.START + timedelta(days=180),
                    120,
                    start_date=self.START,
                    priority=i,
                )
                for i in range(3)
            ]

        totals = {
            weeks: self._solve(projects(), weeks=weeks)[1].total_reassigned_days
            for weeks in (26, 52, 104)
        }

        assert len(set(totals.values())) == 1, totals
        assert totals[26] > 0


class TestDueByHorizon:
    """The budget a project owes before the horizon runs out."""

    START = date(2026, 1, 5)
    WEEKS = 26
    HORIZON_END = START + timedelta(days=26 * 7 - 1)

    def _scheduler(self, project):
        return Scheduler([project], start_date=self.START)

    def _due(self, project):
        return self._scheduler(project)._due_by_horizon(project, self.HORIZON_END)

    def test_deadline_inside_horizon_owes_the_whole_budget(self):
        """There is no later date to work on it, so all of it is due."""
        project = Project("P", self.HORIZON_END - timedelta(days=10), 40)
        assert self._due(project) == 40

    def test_deadline_on_the_boundary_owes_the_whole_budget(self):
        project = Project("P", self.HORIZON_END, 40)
        assert self._due(project) == 40

    def test_deadline_past_horizon_owes_its_paced_share(self):
        """Half the window inside the horizon means about half the budget."""
        project = Project("P", self.HORIZON_END + timedelta(days=182), 100)
        scheduler = self._scheduler(project)

        in_horizon = scheduler._count_weekdays_inclusive(self.START, self.HORIZON_END)
        window = scheduler._count_weekdays_inclusive(self.START, project.end_date)
        assert self._due(project) == int(100 * in_horizon / window)
        assert 0 < self._due(project) < 100

    def test_paced_share_rounds_down(self):
        """Rounding must never invent a day to hand off."""
        project = Project("P", self.HORIZON_END + timedelta(days=100), 7)
        scheduler = self._scheduler(project)

        in_horizon = scheduler._count_weekdays_inclusive(self.START, self.HORIZON_END)
        window = scheduler._count_weekdays_inclusive(self.START, project.end_date)
        assert self._due(project) == int(7 * in_horizon / window)
        assert self._due(project) <= 7 * in_horizon / window

    def test_stale_deadline_owes_nothing(self):
        """A project that expired before the schedule starts is stale data."""
        project = Project("P", self.START - timedelta(days=1), 40)
        assert self._due(project) == 0

    def test_start_after_horizon_owes_nothing(self):
        project = Project(
            "P",
            self.HORIZON_END + timedelta(days=400),
            40,
            start_date=self.HORIZON_END + timedelta(days=1),
        )
        assert self._due(project) == 0

    def test_later_start_owes_less(self):
        """The share is measured from when the project starts, not from today."""
        early = Project(
            "Early", self.HORIZON_END + timedelta(days=200), 60, start_date=self.START
        )
        late = Project(
            "Late",
            self.HORIZON_END + timedelta(days=200),
            60,
            start_date=self.START + timedelta(days=120),
        )
        assert self._due(late) < self._due(early)

    def test_never_owes_more_than_the_budget(self):
        for offset in (-30, 0, 1, 60, 200, 900):
            project = Project("P", self.HORIZON_END + timedelta(days=offset), 40)
            assert 0 <= self._due(project) <= project.slots_remaining


class TestReassignmentInvariants:
    """Properties that must hold for every reassignment solve.

    Swept across scenarios rather than asserted on one, because the failures
    found here (silent zero totals, quota inflation) only showed up in specific
    deadline/horizon combinations.
    """

    START = date(2026, 1, 5)

    SCENARIOS = [
        # (label, deadline offsets, budgets, priorities, weeks)
        ("all past horizon", [400, 400, 400], [120, 120, 120], [0, 1, 2], 26),
        ("all inside horizon", [180, 180, 180], [120, 120, 120], [0, 1, 2], 26),
        ("straddling the boundary", [181, 182, 183], [120, 120, 120], [0, 0, 0], 26),
        ("mixed deadlines", [100, 400, 700], [100, 200, 50], [0, 5, 0], 26),
        ("staggered budgets", [90, 200, 365], [10, 90, 200], [3, 0, 1], 26),
        ("tiny horizon", [400, 400], [60, 60], [0, 1], 13),
        ("long horizon", [700, 900], [200, 300], [0, 0], 78),
        ("one project", [365], [300], [0], 52),
        ("feasible", [365, 365], [20, 20], [0, 0], 52),
        ("equal priorities", [300, 300, 300, 300], [80, 80, 80, 80], [7] * 4, 26),
        ("stale plus live", [-10, 200], [20, 200], [0, 0], 26),
        # Found by sweeping random workloads: both leave capacity idle unless the
        # solver hands back quota days the schedule turned out not to need
        ("quota needs trimming", [348, 247, 390, 287], [41, 137, 118, 88], [100, 0, 5, 5], 52),
        (
            "quota needs trimming, short horizon",
            [181, 111, 178, 386, 333, 109],
            [99, 23, 112, 57, 148, 126],
            [1, 5, 0, 5, 100, 0],
            13,
        ),
    ]

    def _cases(self):
        for label, offsets, budgets, priorities, weeks in self.SCENARIOS:
            projects = [
                Project(
                    f"P{i}",
                    self.START + timedelta(days=offset),
                    budget,
                    start_date=self.START,
                    priority=priority,
                )
                for i, (offset, budget, priority) in enumerate(
                    zip(offsets, budgets, priorities)
                )
            ]
            scheduler = Scheduler(projects, start_date=self.START)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                schedule = scheduler.create_schedule(
                    num_weeks=weeks, method="paced", reassign_days=True
                )
            yield label, scheduler, schedule

    def test_days_are_positive_whole_days(self):
        for label, _, schedule in self._cases():
            for entry in schedule.reassignments:
                assert isinstance(entry.days, int), label
                assert entry.days > 0, label

    def test_bookings_land_inside_the_horizon(self):
        for label, _, schedule in self._cases():
            for entry in schedule.reassignments:
                assert self.START <= entry.date <= schedule.end_date, (
                    f"{label}: {entry.project.name} booked on {entry.date}"
                )

    def test_a_project_never_sheds_more_than_it_has(self):
        """Scheduled plus reassigned can never exceed the budget."""
        for label, scheduler, schedule in self._cases():
            for project in scheduler.projects:
                scheduled = len(schedule.get_project_slots(project))
                reassigned = schedule.reassigned_days_for(project)
                assert reassigned <= project.slots_remaining, label
                assert scheduled + reassigned <= project.slots_remaining, (
                    f"{label}: {project.name} over-booked"
                )

    def test_reassignment_does_not_overshoot_what_was_due(self):
        """A project that sheds days must not be credited past what it owed.

        Scheduled plus reassigned overshooting ``_due_by_horizon`` means days were
        handed off that the project went on to book anyway -- the day is counted
        twice and the worker looks busier than they are. One day of slack is
        allowed for integer rounding of the paced share.
        """
        for label, scheduler, schedule in self._cases():
            for project in scheduler.projects:
                if not schedule.reassigned_days_for(project):
                    continue
                accounted = len(schedule.get_project_slots(project)) + (
                    schedule.reassigned_days_for(project)
                )
                due = scheduler._due_by_horizon(project, schedule.end_date)
                assert accounted <= due + 1, (
                    f"{label}: {project.name} accounted for {accounted} of {due} due"
                )

    def test_stale_projects_are_never_reassigned(self):
        """A deadline in the past is bad data, not work to hand off."""
        for label, scheduler, schedule in self._cases():
            for project in scheduler.projects:
                if project.end_date < self.START:
                    assert schedule.reassigned_days_for(project) == 0, label

    def test_totals_agree_with_the_ledger(self):
        for label, scheduler, schedule in self._cases():
            per_project = sum(
                schedule.reassigned_days_for(p) for p in scheduler.projects
            )
            assert per_project == schedule.total_reassigned_days, label
            assert sum(r.days for r in schedule.reassignments) == (
                schedule.total_reassigned_days
            ), label

    def test_reassignment_never_idles_capacity_it_could_have_used(self):
        """Days are only shed once the horizon is genuinely full."""
        for label, _, schedule in self._cases():
            if schedule.total_reassigned_days == 0:
                continue
            idle = sum(1 for slot in schedule.slots if slot.project is None)
            assert idle == 0, f"{label}: shed days while {idle} workdays sat idle"

    def test_solve_is_deterministic(self):
        """The same workload must always produce the same ledger."""
        def ledger(schedule):
            return [(r.project.name, r.date, r.days) for r in schedule.reassignments]

        for (label, _, first), (_, _, second) in zip(self._cases(), self._cases()):
            assert ledger(first) == ledger(second), label

    def test_enabling_reassignment_does_not_lose_scheduled_work(self):
        """Reassignment reallocates the horizon; it must not waste it."""
        for label, offsets, budgets, priorities, weeks in self.SCENARIOS:
            def build():
                return [
                    Project(
                        f"P{i}",
                        self.START + timedelta(days=offset),
                        budget,
                        start_date=self.START,
                        priority=priority,
                    )
                    for i, (offset, budget, priority) in enumerate(
                        zip(offsets, budgets, priorities)
                    )
                ]

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                off = Scheduler(build(), start_date=self.START).create_schedule(
                    num_weeks=weeks, method="paced"
                )
                on = Scheduler(build(), start_date=self.START).create_schedule(
                    num_weeks=weeks, method="paced", reassign_days=True
                )

            booked_off = sum(1 for s in off.slots if s.project)
            booked_on = sum(1 for s in on.slots if s.project)
            assert booked_on + on.total_reassigned_days >= booked_off, label


class TestReassignmentSolver:
    """The schedule/measure loop that decides how many days to hand off."""

    START = date(2026, 1, 5)

    @staticmethod
    def _past_horizon_projects(n=3, budget=120):
        start = TestReassignmentSolver.START
        return [
            Project(
                f"P{i}",
                start + timedelta(days=400),
                budget,
                start_date=start,
                priority=i,
            )
            for i in range(n)
        ]

    def test_ordinary_oversubscription_converges_quietly(self):
        """No warning: the solver should settle without hitting its cap."""
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            schedule = Scheduler(
                self._past_horizon_projects(), start_date=self.START
            ).create_schedule(num_weeks=26, method="paced", reassign_days=True)

        assert schedule.total_reassigned_days > 0

    def test_single_iteration_cannot_shed_and_says_so(self):
        """The first pass has no quotas, so one iteration reassigns nothing."""
        with pytest.warns(UserWarning, match="behind pace"):
            schedule = Scheduler(
                self._past_horizon_projects(), start_date=self.START
            ).create_schedule(
                num_weeks=26,
                method="paced",
                reassign_days=True,
                max_reassignment_iterations=1,
            )

        assert schedule.total_reassigned_days == 0

    def test_invalid_iteration_cap_rejected(self):
        with pytest.raises(ValueError, match="max_reassignment_iterations"):
            Scheduler(
                self._past_horizon_projects(), start_date=self.START
            ).create_schedule(
                num_weeks=26,
                method="paced",
                reassign_days=True,
                max_reassignment_iterations=0,
            )

    def test_unshedable_shortfall_warns_instead_of_inflating_quotas(self):
        """A capacity-bound project must not be given quota forever.

        Its reassigned days displace days it would have been scheduled, so the
        shortfall never closes. The solver used to grow the quota every pass until
        the cap, handing off days that bought back no time.
        """
        start = self.START
        projects = [
            Project("Tight", start + timedelta(days=104), 109, start_date=start),
            Project("Long", start + timedelta(days=444), 145, start_date=start),
            Project("Top", start + timedelta(days=586), 28, start_date=start, priority=100),
            Project("Bound", start + timedelta(days=207), 106, start_date=start, priority=100),
        ]
        scheduler = Scheduler(projects, start_date=start)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            schedule = scheduler.create_schedule(
                num_weeks=26, method="paced", reassign_days=True
            )

        bound = next(p for p in scheduler.projects if p.name == "Bound")
        due = scheduler._due_by_horizon(bound, schedule.end_date)
        scheduled = len(schedule.get_project_slots(bound))
        # It sheds no more than the gap it was actually short
        assert schedule.reassigned_days_for(bound) <= due - scheduled
        assert any("behind pace" in str(w.message) for w in caught)

    def test_solver_prefers_the_leanest_feasible_pass(self):
        """Quota given back once a project can book its own days is not re-shed."""
        projects = self._past_horizon_projects()
        scheduler = Scheduler(projects, start_date=self.START)
        schedule = scheduler.create_schedule(
            num_weeks=26, method="paced", reassign_days=True
        )

        # Every shed day must still be missing from the project's own progress
        for project in scheduler.projects:
            reassigned = schedule.reassigned_days_for(project)
            if not reassigned:
                continue
            due = scheduler._due_by_horizon(project, schedule.end_date)
            scheduled = len(schedule.get_project_slots(project))
            assert reassigned <= max(0, due - scheduled) + project.slots_remaining - due

    def test_higher_priority_sheds_last_across_the_horizon(self):
        """Priority ordering still decides who gives up days past the horizon."""
        scheduler = Scheduler(self._past_horizon_projects(), start_date=self.START)
        schedule = scheduler.create_schedule(
            num_weeks=26, method="paced", reassign_days=True
        )
        by_name = {p.name: p for p in scheduler.projects}

        assert schedule.reassigned_days_for(by_name["P2"]) <= (
            schedule.reassigned_days_for(by_name["P0"])
        )
        assert schedule.reassigned_days_for(by_name["P0"]) > 0

    def test_cadence_changes_when_not_whether_days_are_shed(self):
        """Every cadence accounts for its days; only the checkpoints differ."""
        totals = {}
        for cadence in (1, 7, 30, 90, 400):
            scheduler = Scheduler(self._past_horizon_projects(), start_date=self.START)
            schedule = scheduler.create_schedule(
                num_weeks=26,
                method="paced",
                reassign_days=True,
                reassignment_cadence_days=cadence,
            )
            totals[cadence] = schedule.total_reassigned_days
            assert sum(r.days for r in schedule.reassignments) == (
                schedule.total_reassigned_days
            )

        assert all(total > 0 for total in totals.values()), totals

    def test_renewal_projects_can_shed_days(self):
        """Generated renewals are budget too, and compete for the same horizon."""
        start = self.START
        projects = [
            Project("R", start + timedelta(days=60), 40, start_date=start, renewal_days=60),
            Project("Hog", start + timedelta(days=400), 200, start_date=start, priority=9),
        ]
        scheduler = Scheduler(projects, start_date=start)
        schedule = scheduler.create_schedule(
            num_weeks=26, method="paced", reassign_days=True
        )

        renewal = next(p for p in scheduler.projects if p.is_renewal)
        assert schedule.reassigned_days_for(renewal) > 0
        assert schedule.reassigned_days_for(renewal) <= renewal.slots_remaining

    def test_zero_day_and_fractional_projects(self):
        """A zero-day project sheds nothing; a fractional one sheds whole days."""
        start = self.START
        projects = [
            Project("Zero", start + timedelta(days=30), 0, start_date=start),
            Project("Half", start + timedelta(days=30), 60.5, start_date=start),
        ]
        scheduler = Scheduler(projects, start_date=start)
        schedule = scheduler.create_schedule(
            num_weeks=26, method="paced", reassign_days=True
        )
        by_name = {p.name: p for p in scheduler.projects}

        assert schedule.reassigned_days_for(by_name["Zero"]) == 0
        assert schedule.reassigned_days_for(by_name["Half"]) > 0
        assert schedule.reassigned_days_for(by_name["Half"]) <= 60

    def test_empty_project_list(self):
        schedule = Scheduler([], start_date=self.START).create_schedule(
            num_weeks=26, method="paced", reassign_days=True
        )
        assert schedule.reassignments == []
        assert schedule.total_reassigned_days == 0

    def test_project_starting_after_the_horizon(self):
        """Work that has not started yet owes nothing inside the horizon."""
        start = self.START
        late = Project(
            "Late",
            start + timedelta(days=500),
            100,
            start_date=start + timedelta(days=300),
        )
        schedule = Scheduler([late], start_date=start).create_schedule(
            num_weeks=26, method="paced", reassign_days=True
        )
        assert schedule.total_reassigned_days == 0

    def test_more_demand_never_sheds_fewer_days(self):
        """Adding projects to an oversubscribed plan can only push more work out."""
        totals = []
        for n in range(1, 6):
            scheduler = Scheduler(
                self._past_horizon_projects(n), start_date=self.START
            )
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                schedule = scheduler.create_schedule(
                    num_weeks=26, method="paced", reassign_days=True
                )
            totals.append(schedule.total_reassigned_days)

        assert totals == sorted(totals), totals
        assert totals[-1] > 0


class TestReassignmentWithRealisticWorkload:
    """A workload shaped like a real worker's file: pending work due past the horizon.

    This is the case the app got wrong -- eleven active projects that fit, plus
    pending ones whose deadlines fall just past a 52-week horizon.
    """

    START = date(2026, 9, 7)
    WEEKS = 52

    @staticmethod
    def _active():
        return [
            Project("PAR 1", date(2026, 12, 24), 15, priority=100000),
            Project("PAR 2", date(2027, 3, 3), 15, priority=1000),
            Project("OPTIC", date(2027, 6, 30), 30),
            Project("HIV", date(2027, 7, 31), 22),
            Project("Calibration", date(2027, 5, 31), 22),
            Project("CRC Costs", date(2027, 3, 31), 17),
            Project("COVID", date(2027, 8, 31), 8),
            Project("MGS", date(2026, 10, 15), 6, priority=10),
            Project("B&P HC", date(2026, 9, 30), 3),
            Project("B&P GER", date(2026, 9, 30), 3),
            Project("BSV", date(2027, 1, 31), 30),
        ]

    @staticmethod
    def _pending():
        return [
            Project("CDC/TGS", date(2027, 10, 20), 50, priority=100, probability=0.9),
            Project("Blueprint", date(2027, 11, 1), 45, probability=0.8),
            Project("CISNET", date(2027, 12, 1), 40, probability=0.7),
            Project("State Dep", date(2027, 12, 1), 40, probability=0.7),
        ]

    def _solve(self, projects):
        scheduler = Scheduler(projects, start_date=self.START)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            schedule = scheduler.create_schedule(
                num_weeks=self.WEEKS, method="paced", reassign_days=True
            )
        return scheduler, schedule

    def test_active_only_workload_fits(self):
        """The active book of work has slack, so nothing needs to move."""
        _, schedule = self._solve(self._active())

        assert schedule.total_reassigned_days == 0
        assert any(slot.project is None for slot in schedule.slots)

    def test_selecting_everything_reassigns_days(self):
        """Selecting all projects used to report zero days to reassign."""
        scheduler, schedule = self._solve(self._active() + self._pending())

        assert schedule.total_reassigned_days > 0
        # The horizon is full: every shed day is one that genuinely did not fit
        assert all(slot.project is not None for slot in schedule.slots)

    def test_pending_work_is_what_gets_shed(self):
        """Deadline-pressured active work keeps its days; speculative work sheds."""
        scheduler, schedule = self._solve(self._active() + self._pending())
        pending_names = {p.name for p in self._pending()}

        shed = {
            p.name: schedule.reassigned_days_for(p)
            for p in scheduler.projects
            if schedule.reassigned_days_for(p)
        }
        assert shed
        # Nothing with a hard near-term deadline should be handed off
        assert "PAR 1" not in shed
        assert "MGS" not in shed
        assert pending_names & set(shed)

    def test_adding_pending_projects_increases_reassignment(self):
        totals = []
        pending = self._pending()
        for count in range(len(pending) + 1):
            _, schedule = self._solve(self._active() + pending[:count])
            totals.append(schedule.total_reassigned_days)

        assert totals == sorted(totals), totals
        assert totals[0] == 0
        assert totals[-1] > 0

    def test_summary_and_table_agree_with_the_schedule(self):
        """What the Reassignment tab totals must match the schedule ledger."""
        from planner.analysis import (
            compute_monthly_reassigned_days,
            create_reassignment_table,
        )

        _, schedule = self._solve(self._active() + self._pending())
        long_format = compute_monthly_reassigned_days(schedule)
        table = create_reassignment_table(schedule)

        assert long_format["reassigned_days"].sum() == schedule.total_reassigned_days
        assert int(table.iloc[-1]["Total"]) == schedule.total_reassigned_days


class TestReassignmentTable:
    """Tests for the project-by-month reassignment table."""

    @staticmethod
    def _schedule_with_reassignments():
        start = date(2026, 1, 5)
        end = start + timedelta(days=180)
        projects = [
            Project(f"P{i}", end, 120, start_date=start, priority=i) for i in range(3)
        ]
        scheduler = Scheduler(projects, start_date=start)
        return scheduler.create_schedule(
            num_weeks=26, method="paced", reassign_days=True
        )

    def test_monthly_long_format(self):
        """Long-format output totals to the schedule's reassigned days."""
        from planner.analysis import compute_monthly_reassigned_days

        schedule = self._schedule_with_reassignments()
        df = compute_monthly_reassigned_days(schedule)

        assert list(df.columns) == [
            "year",
            "month",
            "month_name",
            "project",
            "reassigned_days",
        ]
        assert df["reassigned_days"].sum() == schedule.total_reassigned_days

    def test_table_shape_and_totals(self):
        """Rows are projects plus a total row; columns span the horizon."""
        from planner.analysis import create_reassignment_table

        schedule = self._schedule_with_reassignments()
        table = create_reassignment_table(schedule)

        assert table.columns[0] == "Project"
        assert table.columns[-1] == "Total"
        assert table.iloc[-1]["Project"] == "Total"
        assert int(table.iloc[-1]["Total"]) == schedule.total_reassigned_days

        # One column per month in the horizon, between Project and Total
        months = len(table.columns) - 2
        assert months == 7  # Jan 2026 through Jul 2026

    def test_empty_when_nothing_reassigned(self):
        """A schedule without reassignments yields a table with no rows."""
        from planner.analysis import (
            compute_monthly_reassigned_days,
            create_reassignment_table,
        )

        start = date(2026, 1, 5)
        projects = [Project("Small", start + timedelta(days=180), 20, start_date=start)]
        schedule = Scheduler(projects, start_date=start).create_schedule(
            num_weeks=26, method="paced", reassign_days=True
        )

        assert compute_monthly_reassigned_days(schedule).empty
        table = create_reassignment_table(schedule)
        assert table.empty
        assert list(table.columns)[0] == "Project"


class TestPacedPriority:
    """Paced scheduling must honor project priority, not just pacing credit."""

    @staticmethod
    def _contending_projects(favored_priority):
        """Three identical, oversubscribed projects; one may be favored."""
        start = date(2026, 1, 5)  # Monday
        end = start + timedelta(days=180)
        return [
            Project(
                name,
                end,
                120,
                start_date=start,
                priority=favored_priority if name == "Favored" else 0,
            )
            for name in ("Favored", "Other A", "Other B")
        ]

    def _run(self, favored_priority):
        start = date(2026, 1, 5)
        projects = self._contending_projects(favored_priority)
        scheduler = Scheduler(projects, start_date=start)
        schedule = scheduler.create_schedule(
            num_weeks=26, method="paced", reassign_days=True
        )
        favored = next(p for p in scheduler.projects if p.name == "Favored")
        return schedule, favored

    def test_priority_wins_slots_under_contention(self):
        """A higher-priority project is scheduled more than its equal-sized peers."""
        schedule, favored = self._run(favored_priority=10)

        favored_days = len(schedule.get_project_slots(favored))
        others = [
            len(schedule.get_project_slots(p))
            for p in {s.project for s in schedule.slots if s.project}
            if p.name != "Favored"
        ]
        assert favored_days > max(others)

    def test_priority_reduces_reassigned_days(self):
        """Raising priority moves reassignment off that project onto the rest."""
        baseline, baseline_favored = self._run(favored_priority=0)
        raised, raised_favored = self._run(favored_priority=10)

        assert raised.reassigned_days_for(
            raised_favored
        ) < baseline.reassigned_days_for(baseline_favored)

    def test_priority_is_ordinal_not_a_magnitude(self):
        """Only the ranking matters, so any winning priority behaves the same."""
        low, low_favored = self._run(favored_priority=5)
        high, high_favored = self._run(favored_priority=100)

        assert low.reassigned_days_for(low_favored) == high.reassigned_days_for(
            high_favored
        )

    def test_deadline_feasibility_outranks_a_roomy_high_priority_project(self):
        """A deadline-critical project keeps its days against a project with slack.

        ``Roomy`` has the higher priority but is nowhere near needing every
        workday, so the feasibility guards protect ``Urgent`` regardless.
        """
        start = date(2026, 1, 5)
        urgent = Project("Urgent", start + timedelta(days=13), 10, start_date=start)
        roomy = Project(
            "Roomy", start + timedelta(days=180), 40, start_date=start, priority=50
        )
        scheduler = Scheduler([urgent, roomy], start_date=start)
        schedule = scheduler.create_schedule(
            num_weeks=26, method="paced", reassign_days=True
        )

        assert len(schedule.get_project_slots(urgent)) == urgent.slots_remaining
        assert schedule.reassigned_days_for(urgent) == 0

    def test_priority_decides_who_sheds_days_when_all_are_infeasible(self):
        """When every project needs every workday, priority keeps its budget."""
        start = date(2026, 1, 5)
        # Both need more days than the window holds, so one of them must shed
        favored = Project(
            "Favored", start + timedelta(days=30), 30, start_date=start, priority=10
        )
        other = Project("Other", start + timedelta(days=30), 30, start_date=start)
        scheduler = Scheduler([favored, other], start_date=start)
        schedule = scheduler.create_schedule(
            num_weeks=26, method="paced", reassign_days=True
        )

        assert len(schedule.get_project_slots(favored)) > len(
            schedule.get_project_slots(other)
        )
        assert schedule.reassigned_days_for(favored) < schedule.reassigned_days_for(
            other
        )
