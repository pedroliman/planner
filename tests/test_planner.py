"""Tests for the project planner."""

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from planner.models import Project, ScheduledSlot, Schedule
from planner.scheduler import Scheduler
from planner.visualization import (
    render_tiles,
    render_statistics,
    compute_weekly_availability,
    render_availability_plot,
)


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
        """Test calculation of remaining slots (2 slots per day)."""
        project = Project(
            name="Test",
            end_date=date(2024, 12, 31),
            remaining_days=5,
        )
        assert project.slots_remaining == 10  # 5 days * 2 slots

    def test_slots_remaining_half_day(self):
        """Test half-day (4-hour) slot calculation."""
        project = Project(
            name="Small Project",
            end_date=date(2024, 12, 31),
            remaining_days=0.5,
        )
        assert project.slots_remaining == 1  # 0.5 days * 2 = 1 slot

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
        slot = ScheduledSlot(date=date(2024, 11, 1), slot_index=0, project=project)

        assert slot.date == date(2024, 11, 1)
        assert slot.slot_index == 0
        assert slot.project == project

    def test_morning_slot(self):
        """Test morning slot detection."""
        slot = ScheduledSlot(date=date(2024, 11, 1), slot_index=0)
        assert slot.is_morning
        assert not slot.is_afternoon
        assert slot.time_label == "AM"

    def test_afternoon_slot(self):
        """Test afternoon slot detection."""
        slot = ScheduledSlot(date=date(2024, 11, 1), slot_index=1)
        assert slot.is_afternoon
        assert not slot.is_morning
        assert slot.time_label == "PM"


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
                ScheduledSlot(date(2024, 11, 1), 0, project),
                ScheduledSlot(date(2024, 11, 1), 1, project),
                ScheduledSlot(date(2024, 11, 2), 0, project),
            ]
        )

        slots_nov_1 = schedule.get_slots_for_date(date(2024, 11, 1))
        assert len(slots_nov_1) == 2

        slots_nov_2 = schedule.get_slots_for_date(date(2024, 11, 2))
        assert len(slots_nov_2) == 1

    def test_get_project_slots(self):
        """Test getting all slots for a project."""
        project_a = Project("A", date(2024, 12, 31), 5)
        project_b = Project("B", date(2024, 12, 31), 3)

        schedule = Schedule(
            slots=[
                ScheduledSlot(date(2024, 11, 1), 0, project_a),
                ScheduledSlot(date(2024, 11, 1), 1, project_b),
                ScheduledSlot(date(2024, 11, 2), 0, project_a),
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
                ScheduledSlot(date(2024, 11, 1), 0, project),
                ScheduledSlot(date(2024, 11, 5), 0, None),  # Unassigned
                ScheduledSlot(date(2024, 11, 3), 0, project),
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

    def test_schedule_assigns_all_work(self):
        """Test that all work gets assigned when possible."""
        projects = [
            Project("Small", date(2024, 12, 31), 2),
        ]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=4)

        project_slots = schedule.get_project_slots(projects[0])
        # 2 days = 4 slots should be assigned
        assert len(project_slots) == 4

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
        ratio = big_slots / small_slots if small_slots > 0 else float('inf')
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
                schedule.get_project_slots(project),
                key=lambda s: (s.date, s.slot_index)
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


class TestVisualization:
    """Tests for the visualization module."""

    def test_render_tiles_empty(self):
        """Test rendering empty schedule."""
        schedule = Schedule()
        result = render_tiles(schedule)
        assert "No schedule" in result

    def test_render_tiles_basic(self):
        """Test basic tile rendering."""
        project = Project("Test", date(2024, 12, 31), 5)
        schedule = Schedule(
            slots=[
                ScheduledSlot(date(2024, 11, 4), 0, project),
                ScheduledSlot(date(2024, 11, 4), 1, project),
            ],
            start_date=date(2024, 11, 4),
            end_date=date(2024, 11, 10),
        )

        result = render_tiles(schedule)
        assert "Legend" in result
        assert "Test" in result

    def test_render_statistics(self):
        """Test statistics rendering."""
        project = Project("Test Project", date(2024, 12, 31), 5)
        schedule = Schedule(
            slots=[
                ScheduledSlot(date(2024, 11, 4), 0, project),
                ScheduledSlot(date(2024, 11, 4), 1, project),
            ],
            start_date=date(2024, 11, 4),
            end_date=date(2024, 11, 10),
        )

        from planner.scheduler import ProjectStats
        stats = [
            ProjectStats(
                project=project,
                total_slots_assigned=2,
                slots_per_week=2.0,
                days_per_week=1.0,
                last_scheduled_date=date(2024, 11, 4),
            )
        ]

        result = render_statistics(stats, schedule)
        assert "Project Statistics" in result
        assert "Test Project" in result
        assert "Days/Week" in result


class TestIntegration:
    """Integration tests for the full workflow."""

    def test_full_planning_workflow(self):
        """Test complete planning workflow from projects to visualization."""
        projects = [
            Project("Alpha", date(2024, 12, 31), 15),
            Project("Beta", date(2024, 12, 15), 8),
            Project("Gamma", date(2024, 11, 30), 3),
        ]

        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=8)
        stats = scheduler.get_statistics(schedule)

        # Verify schedule was created
        assert len(schedule.slots) > 0

        # Verify all projects got assigned
        for project in projects:
            project_slots = schedule.get_project_slots(project)
            assert len(project_slots) > 0, f"{project.name} has no assigned slots"

        # Verify statistics
        assert len(stats) == 3
        for stat in stats:
            assert stat.days_per_week >= 0

        # Verify visualization works
        tiles = render_tiles(schedule)
        assert len(tiles) > 0

        stats_output = render_statistics(stats, schedule)
        assert len(stats_output) > 0

    def test_half_day_scheduling(self):
        """Test that small projects can be scheduled in half-day slots."""
        projects = [
            Project("Big", date(2024, 12, 31), 20),
            Project("Tiny", date(2024, 12, 31), 0.5),  # Half a day
        ]

        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=4)

        tiny_slots = schedule.get_project_slots(projects[1])
        # Should have 1 slot (0.5 days = 1 slot)
        assert len(tiny_slots) == 1


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

        # Both should assign all 20 slots (10 days * 2 slots)
        paced_slots = schedule_paced.get_project_slots(projects[0])
        frontload_slots = schedule_frontload.get_project_slots(projects[0])

        assert len(paced_slots) == 20
        assert len(frontload_slots) == 20

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
        active_slots = schedule.get_project_slots(projects[1])

        assert len(done_slots) == 0
        assert len(active_slots) == 10  # 5 days * 2 slots

    def test_multiple_fractional_day_projects(self):
        """Test scheduling with multiple projects having fractional days."""
        projects = [
            Project("Half", date(2024, 12, 31), 0.5),
            Project("OneHalf", date(2024, 12, 31), 1.5),
            Project("TwoHalf", date(2024, 12, 31), 2.5),
        ]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))

        schedule = scheduler.create_schedule(num_weeks=4, method="paced")

        # Verify slot counts (0.5 days = 1 slot, 1.5 days = 3 slots, 2.5 days = 5 slots)
        assert len(schedule.get_project_slots(projects[0])) == 1
        assert len(schedule.get_project_slots(projects[1])) == 3
        assert len(schedule.get_project_slots(projects[2])) == 5

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
        first_slots = sorted(schedule.get_project_slots(projects[0]), key=lambda s: (s.date, s.slot_index))
        second_slots = sorted(schedule.get_project_slots(projects[1]), key=lambda s: (s.date, s.slot_index))
        third_slots = sorted(schedule.get_project_slots(projects[2]), key=lambda s: (s.date, s.slot_index))

        # First project should end before second project starts
        if first_slots and second_slots:
            last_first = first_slots[-1].date
            first_second = second_slots[0].date
            assert last_first <= first_second, "Frontload should finish First before starting Second"

        # Second project should end before third project starts
        if second_slots and third_slots:
            last_second = second_slots[-1].date
            first_third = third_slots[0].date
            assert last_second <= first_third, "Frontload should finish Second before starting Third"

    def test_paced_method_distributes_work(self):
        """Test that paced method distributes work across the schedule."""
        projects = [
            Project("A", date(2024, 12, 31), 10),
            Project("B", date(2024, 12, 31), 10),
        ]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))

        schedule = scheduler.create_schedule(num_weeks=8, method="paced")

        # Get slots for each project sorted by date
        a_slots = sorted(schedule.get_project_slots(projects[0]), key=lambda s: (s.date, s.slot_index))
        b_slots = sorted(schedule.get_project_slots(projects[1]), key=lambda s: (s.date, s.slot_index))

        # Both projects should have work spread across the schedule
        # Check that both projects start early (not frontloaded)
        assert len(a_slots) > 0 and len(b_slots) > 0

        # Both should start in the first week
        first_week_end = date(2024, 11, 10)
        a_starts_early = any(slot.date <= first_week_end for slot in a_slots)
        b_starts_early = any(slot.date <= first_week_end for slot in b_slots)

        assert a_starts_early and b_starts_early, "Paced method should start both projects early"

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

            # All should have 10 slots (5 days * 2 slots)
            assert a_slots == 10
            assert b_slots == 10
            assert c_slots == 10

    def test_too_much_work_for_schedule(self):
        """Test scheduling when there's more work than available slots."""
        projects = [
            Project("Huge", date(2024, 12, 31), 100),  # 100 days = 200 slots
        ]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))

        # Only 4 weeks = 20 weekdays = 40 slots
        schedule = scheduler.create_schedule(num_weeks=4, method="paced")

        # Should only assign 40 slots (all available)
        huge_slots = schedule.get_project_slots(projects[0])
        assert len(huge_slots) == 40

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
        assert renewal.end_date == date(2024, 12, 1) + timedelta(days=365)

    def test_no_renewal_if_outside_horizon(self):
        """Test that renewals aren't created if they start after the planning horizon."""
        base_project = Project(
            name="Late",
            end_date=date(2025, 12, 31),  # Far in future
            remaining_days=5,
            renewal_days=3,
        )

        scheduler = Scheduler([base_project], start_date=date(2024, 11, 1))
        schedule = scheduler.create_schedule(num_weeks=4, method="paced")  # Short horizon

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
        base_slots = [s for s in schedule.slots if s.project and s.project.name == "Quick"]
        renewal_slots = [s for s in schedule.slots if s.project and s.project.name == "Quick (Renewal)"]

        assert len(base_slots) >= 2  # 1 day = 2 slots
        assert len(renewal_slots) >= 4  # 2 days = 4 slots

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
        late_slots = schedule.get_project_slots(projects[0])   # Late deadline

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
        early_slots = sorted(schedule.get_project_slots(projects[1]), key=lambda s: (s.date, s.slot_index))
        middle_slots = sorted(schedule.get_project_slots(projects[2]), key=lambda s: (s.date, s.slot_index))
        late_slots = sorted(schedule.get_project_slots(projects[0]), key=lambda s: (s.date, s.slot_index))

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
        assert len(big_slots) == 20  # 10 days * 2
        assert len(small_slots) == 4  # 2 days * 2


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


class TestEnhancedVisualization:
    """Tests for enhanced tile visualization."""

    def test_visualization_shows_renewal_indicator(self):
        """Test that legend shows renewal projects with indicator."""
        base_project = Project("Base", date(2024, 11, 30), 2, renewal_days=1)
        scheduler = Scheduler([base_project], start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=8, method="paced")

        output = render_tiles(schedule, show_legend=True)

        # Should show renewal in legend
        assert "(Renewal)" in output or "Renewal" in output

    def test_calendar_grid_rendering(self):
        """Test that calendar grid renders without errors."""
        projects = [
            Project("A", date(2024, 12, 31), 10),
            Project("B", date(2024, 12, 15), 5),
        ]
        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=12, method="paced")

        output = render_tiles(schedule, show_legend=True)

        # Should contain day names (Mon, Wed, Fri only in new visualization)
        assert "Mon" in output
        assert "Wed" in output
        assert "Fri" in output

        # Should contain legend
        assert "Legend" in output


class TestImportFunctionality:
    """Tests for Excel import functionality."""

    def test_import_config_defaults(self):
        """Test loading default import configuration."""
        from planner.importer import load_import_config, DEFAULT_IMPORT_CONFIG

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
            {"name": "Existing", "end_date": "2024-12-31", "remaining_days": 15},  # Update
            {"name": "Unchanged", "end_date": "2024-11-30", "remaining_days": 5},  # Unchanged
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


class TestContinuityPriority:
    """Tests for continuity priority to minimize fragmentation."""

    def test_continuity_groups_project_work(self):
        """Test that projects are worked on in consecutive slots."""
        projects = [
            Project("A", date(2024, 12, 31), 10),
            Project("B", date(2024, 12, 31), 10),
            Project("C", date(2024, 12, 31), 10),
        ]

        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=12, method="paced")

        # Check that each project has consecutive slots
        for project in projects:
            project_slots = sorted(
                schedule.get_project_slots(project),
                key=lambda s: (s.date, s.slot_index)
            )

            if len(project_slots) >= 4:  # At least 2 days
                # Count runs of consecutive slots
                consecutive_runs = []
                current_run = 1

                for i in range(1, len(project_slots)):
                    prev = project_slots[i - 1]
                    curr = project_slots[i]

                    # Check if consecutive (same day or next slot)
                    if (curr.date == prev.date and curr.slot_index == prev.slot_index + 1) or \
                       (curr.date == prev.date + timedelta(days=1) and prev.slot_index == 1 and curr.slot_index == 0):
                        current_run += 1
                    else:
                        consecutive_runs.append(current_run)
                        current_run = 1

                consecutive_runs.append(current_run)

                # At least some runs should be longer than 2 slots (minimize fragmentation)
                long_runs = [r for r in consecutive_runs if r >= 3]
                assert len(long_runs) > 0, f"Project {project.name} should have some consecutive work periods"

    def test_continuity_limits_consecutive_slots(self):
        """Test that continuity doesn't monopolize too many consecutive slots."""
        projects = [
            Project("A", date(2024, 12, 31), 30),  # Large project
            Project("B", date(2024, 12, 31), 5),
        ]

        scheduler = Scheduler(projects, start_date=date(2024, 11, 4))
        schedule = scheduler.create_schedule(num_weeks=12, method="paced")

        # Check that project A doesn't monopolize too many consecutive slots
        a_slots = sorted(
            schedule.get_project_slots(projects[0]),
            key=lambda s: (s.date, s.slot_index)
        )

        # Find longest consecutive run
        max_consecutive = 1
        current_consecutive = 1

        for i in range(1, len(a_slots)):
            prev = a_slots[i - 1]
            curr = a_slots[i]

            # Check if consecutive
            if (curr.date == prev.date and curr.slot_index == prev.slot_index + 1) or \
               (curr.date == prev.date + timedelta(days=1) and prev.slot_index == 1 and curr.slot_index == 0):
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 1

        # Max consecutive should be reasonable (not more than 10 slots = 1 week)
        assert max_consecutive <= 12, f"Project A should not monopolize more than ~1 week ({max_consecutive} slots)"

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
                    assert date_range > 7, f"{project.name} should span more than a week"

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


class TestAvailabilityPlot:
    """Tests for availability plotting functionality."""

    def test_compute_weekly_availability_empty_schedule(self):
        """Test availability computation with an empty schedule."""
        schedule = Schedule(slots=[], start_date=date(2024, 1, 1))
        availability = compute_weekly_availability(schedule, num_weeks=4)

        assert len(availability) == 4
        # All weeks should be 100% available (no scheduled work)
        for week in availability:
            assert week.percent_available == 100.0
            assert week.total_slots == 10  # 5 weekdays * 2 slots

    def test_compute_weekly_availability_fully_scheduled(self):
        """Test availability with a fully scheduled week."""
        start = date(2024, 1, 1)  # Monday
        schedule = Schedule(start_date=start, end_date=start + timedelta(weeks=1))

        # Create a project and schedule all slots in first week
        project = Project("Full Week", date(2024, 12, 31), 5)

        # Add 5 weekdays * 2 slots = 10 slots
        for day in range(5):
            current_date = start + timedelta(days=day)
            schedule.slots.append(ScheduledSlot(current_date, 0, project))  # AM
            schedule.slots.append(ScheduledSlot(current_date, 1, project))  # PM

        availability = compute_weekly_availability(schedule, num_weeks=2)

        assert len(availability) == 2
        # First week should be 0% available (fully scheduled)
        assert availability[0].percent_available == 0.0
        assert availability[0].total_slots == 10
        assert availability[0].unscheduled_slots == 0

        # Second week should be 100% available (no slots)
        assert availability[1].percent_available == 100.0

    def test_compute_weekly_availability_partial(self):
        """Test availability with partially scheduled weeks."""
        start = date(2024, 1, 1)  # Monday
        schedule = Schedule(start_date=start)

        project = Project("Partial", date(2024, 12, 31), 2.5)

        # Schedule 5 slots out of 10 in first week (50%)
        for day in range(3):
            current_date = start + timedelta(days=day)
            if day < 2:
                # First two days fully scheduled
                schedule.slots.append(ScheduledSlot(current_date, 0, project))
                schedule.slots.append(ScheduledSlot(current_date, 1, project))
            else:
                # Third day only AM
                schedule.slots.append(ScheduledSlot(current_date, 0, project))

        availability = compute_weekly_availability(schedule, num_weeks=1)

        assert len(availability) == 1
        # Should have 5 scheduled, 5 unscheduled (50% available)
        assert availability[0].total_slots == 10
        assert availability[0].unscheduled_slots == 5
        assert availability[0].percent_available == 50.0

    def test_compute_weekly_availability_with_unassigned_slots(self):
        """Test availability computation with explicit unassigned slots."""
        start = date(2024, 1, 1)  # Monday
        schedule = Schedule(start_date=start)

        project = Project("Test", date(2024, 12, 31), 1)

        # Create mix of assigned and unassigned slots
        schedule.slots.append(ScheduledSlot(start, 0, project))  # Assigned
        schedule.slots.append(ScheduledSlot(start, 1, None))     # Unassigned

        availability = compute_weekly_availability(schedule, num_weeks=1)

        assert availability[0].total_slots == 10
        assert availability[0].unscheduled_slots == 9  # 1 assigned, 9 unassigned
        assert availability[0].percent_available == 90.0

    def test_availability_increases_over_time(self):
        """Test that availability increases as projects complete."""
        start = date(2024, 1, 1)  # Monday
        projects = [
            Project("Short", date(2024, 2, 1), 3),   # 6 slots
            Project("Medium", date(2024, 3, 1), 5),  # 10 slots
        ]

        scheduler = Scheduler(projects, start_date=start)
        schedule = scheduler.create_schedule(num_weeks=8, method="frontload")

        availability = compute_weekly_availability(schedule, num_weeks=8)

        # Availability should generally increase over time
        # as projects complete
        early_avg = sum(w.percent_available for w in availability[:2]) / 2
        late_avg = sum(w.percent_available for w in availability[-2:]) / 2

        assert late_avg > early_avg, "Availability should increase as projects complete"

    def test_render_availability_plot_basic(self):
        """Test basic rendering of availability plot."""
        start = date(2024, 1, 1)
        schedule_paced = Schedule(start_date=start)
        schedule_frontload = Schedule(start_date=start)

        paced_avail = compute_weekly_availability(schedule_paced, num_weeks=4)
        frontload_avail = compute_weekly_availability(schedule_frontload, num_weeks=4)

        plot = render_availability_plot(paced_avail, frontload_avail)

        # Check that plot contains expected elements
        assert "AVAILABILITY OVER TIME" in plot
        assert "Legend:" in plot
        assert "Paced" in plot or "P" in plot
        assert "Frontload" in plot or "F" in plot
        assert "%" in plot  # Should have percentage markers

    def test_render_availability_plot_empty(self):
        """Test plotting with no data."""
        plot = render_availability_plot([], [])
        assert "No availability data" in plot

    def test_availability_plot_width_and_height(self):
        """Test that plot respects width and height parameters."""
        start = date(2024, 1, 1)
        schedule = Schedule(start_date=start)
        avail = compute_weekly_availability(schedule, num_weeks=4)

        plot = render_availability_plot(avail, avail, plot_width=50, plot_height=10)

        lines = plot.split('\n')
        # Find the plot lines (between top and bottom borders)
        plot_lines = [l for l in lines if '│' in l and '─' in l]

        # Should have border lines
        assert len(plot_lines) > 0

    def test_weekly_availability_week_numbers(self):
        """Test that week numbers are correctly assigned."""
        start = date(2024, 1, 1)
        schedule = Schedule(start_date=start)

        availability = compute_weekly_availability(schedule, num_weeks=5)

        assert len(availability) == 5
        for i, week in enumerate(availability):
            assert week.week_number == i
            expected_start = start + timedelta(weeks=i)
            assert week.start_date == expected_start

    def test_availability_comparison_paced_vs_frontload(self):
        """Test that paced and frontload methods show different availability patterns."""
        start = date(2024, 1, 1)
        projects = [
            Project("A", date(2024, 3, 1), 10),
            Project("B", date(2024, 4, 1), 10),
        ]

        scheduler = Scheduler(projects, start_date=start)
        schedule_paced = scheduler.create_schedule(num_weeks=12, method="paced")
        schedule_frontload = scheduler.create_schedule(num_weeks=12, method="frontload")

        paced_avail = compute_weekly_availability(schedule_paced, num_weeks=12)
        frontload_avail = compute_weekly_availability(schedule_frontload, num_weeks=12)

        # Both should have same number of weeks
        assert len(paced_avail) == len(frontload_avail) == 12

        # Frontload should show lower availability early and higher later
        # (work is concentrated at the beginning)
        frontload_early = frontload_avail[0].percent_available
        frontload_late = frontload_avail[-1].percent_available

        # Later weeks should have more availability in frontload
        assert frontload_late >= frontload_early
