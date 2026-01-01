"""Command-line interface for the project planner."""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from planner.models import Project
from planner.scheduler import Scheduler
from planner.visualization import render_tiles, render_statistics


DEFAULT_CONFIG_FILE = "projects.json"


def load_projects(config_path: str) -> list[Project]:
    """Load projects from a JSON configuration file.

    Expected format:
    {
        "projects": [
            {
                "name": "Project A",
                "end_date": "2024-12-31",
                "remaining_days": 10
            }
        ]
    }
    """
    path = Path(config_path)
    if not path.exists():
        print(f"Error: Configuration file '{config_path}' not found.")
        print(f"Create a {DEFAULT_CONFIG_FILE} file with your projects.")
        print("\nExample format:")
        print(json.dumps({
            "projects": [
                {"name": "Project A", "end_date": "2024-12-31", "remaining_days": 10},
                {"name": "Project B", "end_date": "2024-11-15", "remaining_days": 5},
            ]
        }, indent=2))
        sys.exit(1)

    with open(path) as f:
        data = json.load(f)

    projects = []
    for i, p in enumerate(data.get("projects", [])):
        end_date = datetime.strptime(p["end_date"], "%Y-%m-%d").date()
        project = Project(
            name=p["name"],
            end_date=end_date,
            remaining_days=float(p["remaining_days"]),
            _color_index=i,
        )
        projects.append(project)

    return projects


def cmd_plan(args: argparse.Namespace) -> None:
    """Run the planning algorithm and display results."""
    projects = load_projects(args.config)

    if not projects:
        print("No projects found in configuration file.")
        return

    print(f"Planning {len(projects)} projects starting from {date.today()}")
    print()

    # Create scheduler
    scheduler = Scheduler(projects, start_date=date.today())

    # Generate both schedules
    schedule_paced = scheduler.create_schedule(num_weeks=args.weeks, method="paced")
    schedule_frontload = scheduler.create_schedule(num_weeks=args.weeks, method="frontload")

    # Determine which schedule to show tiles for
    selected_method = args.method
    selected_schedule = schedule_paced if selected_method == "paced" else schedule_frontload

    # Display tile visualization for selected method only
    print(f"📅 Schedule Visualization ({selected_method.upper()} method)")
    print("=" * 60)
    print(render_tiles(selected_schedule))
    print()

    # Display statistics for both methods
    print("=" * 60)
    print("📊 STATISTICS COMPARISON")
    print("=" * 60)
    print()

    stats_paced = scheduler.get_statistics(schedule_paced)
    stats_frontload = scheduler.get_statistics(schedule_frontload)

    print("🎯 PACED METHOD (default)")
    print("-" * 60)
    print(render_statistics(stats_paced, schedule_paced))
    print()

    print("⚡ FRONTLOAD METHOD")
    print("-" * 60)
    print(render_statistics(stats_frontload, schedule_frontload))


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize a sample configuration file."""
    config_path = Path(args.config)

    if config_path.exists() and not args.force:
        print(f"Configuration file '{args.config}' already exists.")
        print("Use --force to overwrite.")
        return

    current_year = date.today().year
    sample_config = {
        "projects": [
            {
                "name": "Project Alpha",
                "end_date": date(current_year, 12, 31).isoformat(),
                "remaining_days": 15,
            },
            {
                "name": "Project Beta",
                "end_date": date(current_year, 12, 15).isoformat(),
                "remaining_days": 8,
            },
            {
                "name": "Project Gamma",
                "end_date": date(current_year, 11, 30).isoformat(),
                "remaining_days": 3,
            },
        ]
    }

    with open(config_path, "w") as f:
        json.dump(sample_config, f, indent=2)

    print(f"Created sample configuration file: {args.config}")
    print("Edit this file to add your projects, then run 'planner plan'")


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="planner",
        description="A minimalist project planner with GitHub-style tile visualization",
    )
    parser.add_argument(
        "-c", "--config",
        default=DEFAULT_CONFIG_FILE,
        help=f"Path to configuration file (default: {DEFAULT_CONFIG_FILE})",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # plan command
    plan_parser = subparsers.add_parser("plan", help="Generate and display project schedule")
    plan_parser.add_argument(
        "-w", "--weeks",
        type=int,
        default=12,
        help="Number of weeks to plan ahead (default: 12)",
    )
    plan_parser.add_argument(
        "-m", "--method",
        choices=["paced", "frontload"],
        default="paced",
        help="Scheduling method: 'paced' (default, balanced) or 'frontload' (concentrated)",
    )
    plan_parser.set_defaults(func=cmd_plan)

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize a sample configuration file")
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing configuration file",
    )
    init_parser.set_defaults(func=cmd_init)

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
