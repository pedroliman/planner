"""Data models for the project planner."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional


# Default color palette for projects
DEFAULT_COLORS = [
    "\033[92m",  # Green
    "\033[94m",  # Blue
    "\033[93m",  # Yellow
    "\033[95m",  # Magenta
    "\033[96m",  # Cyan
    "\033[91m",  # Red
]

RESET_COLOR = "\033[0m"


@dataclass
class Project:
    """A project with scheduling requirements.

    Attributes:
        name: The project name
        end_date: The deadline for the project
        remaining_days: Number of full days of work remaining
        start_date: When the project starts (defaults to today if not specified)
        renewal_days: If set, creates a renewal project with this many days after completion
        is_renewal: Internal flag to track if this is a renewal project
        parent_name: Name of the parent project if this is a renewal
        color: ANSI color code for visualization (auto-assigned if not provided)
    """

    name: str
    end_date: date
    remaining_days: float  # Can be fractional for half-days
    start_date: Optional[date] = None
    renewal_days: Optional[float] = None
    is_renewal: bool = False
    parent_name: Optional[str] = None
    color: Optional[str] = None
    _color_index: int = field(default=0, repr=False)

    def __post_init__(self):
        if self.color is None:
            self.color = DEFAULT_COLORS[self._color_index % len(DEFAULT_COLORS)]

    @property
    def slots_remaining(self) -> int:
        """Number of 8-hour slots remaining (1 slot per day)."""
        return int(self.remaining_days)

    def days_until_deadline(self, from_date: date) -> int:
        """Calculate working days until the deadline."""
        return (self.end_date - from_date).days

    def __hash__(self):
        return hash(self.name)


@dataclass
class ScheduledSlot:
    """An 8-hour day slot assigned to a project.

    Attributes:
        date: The date of the slot
        project: The assigned project (None if unassigned)
    """

    date: date
    project: Optional[Project] = None


@dataclass
class Schedule:
    """A complete schedule of project work.

    Attributes:
        slots: List of scheduled slots
        start_date: First date in the schedule
        end_date: Last date in the schedule
    """

    slots: list[ScheduledSlot] = field(default_factory=list)
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    def get_slots_for_date(self, target_date: date) -> list[ScheduledSlot]:
        """Get all slots for a specific date."""
        return [s for s in self.slots if s.date == target_date]

    def get_project_slots(self, project: Project) -> list[ScheduledSlot]:
        """Get all slots assigned to a project."""
        return [s for s in self.slots if s.project == project]

    def get_unique_dates(self) -> list[date]:
        """Get all unique dates in the schedule, sorted."""
        return sorted(set(s.date for s in self.slots))

    def get_last_work_date(self) -> Optional[date]:
        """Get the last date with assigned work."""
        assigned_slots = [s for s in self.slots if s.project is not None]
        if not assigned_slots:
            return None
        return max(s.date for s in assigned_slots)
