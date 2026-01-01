"""Tests for the project planner."""

from datetime import date, timedelta

import pytest

from planner.models import Project, ScheduledSlot, Schedule
from planner.scheduler import Scheduler
from planner.visualization import render_tiles, render_statistics


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
        assert "PROJECT STATISTICS" in result
        assert "Test Project" in result
        assert "days/week" in result


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
