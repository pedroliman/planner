"""Command-line interface for the project planner."""

import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.text import Text

from planner.models import Project
from planner.scheduler import Scheduler
from planner.visualization import (
    render_tiles,
    render_statistics,
    compute_weekly_availability,
    render_availability_plot,
)
from planner.importer import (
    read_excel_projects,
    update_projects_json,
    load_import_config,
    save_default_import_config,
)


DEFAULT_CONFIG_FILE = "projects.json"
DEFAULT_IMPORT_CONFIG_FILE = "import_config.json"

console = Console()


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
        console.print(f"[red]Error:[/red] Configuration file '{config_path}' not found.")
        console.print(f"\n[yellow]Create a {DEFAULT_CONFIG_FILE} file with your projects.[/yellow]")

        example = {
            "projects": [
                {"name": "Project A", "end_date": "2024-12-31", "remaining_days": 10},
                {"name": "Project B", "end_date": "2024-11-15", "remaining_days": 5},
            ]
        }

        console.print("\n[bold]Example format:[/bold]")
        console.print(Panel(json.dumps(example, indent=2), border_style="blue"))
        sys.exit(1)

    with open(path) as f:
        data = json.load(f)

    projects = []
    for i, p in enumerate(data.get("projects", [])):
        end_date = datetime.strptime(p["end_date"], "%Y-%m-%d").date()

        # Parse optional start_date
        start_date = None
        if "start_date" in p and p["start_date"]:
            start_date = datetime.strptime(p["start_date"], "%Y-%m-%d").date()

        # Parse optional renewal_days
        renewal_days = None
        if "renewal_days" in p and p["renewal_days"]:
            renewal_days = float(p["renewal_days"])

        project = Project(
            name=p["name"],
            end_date=end_date,
            remaining_days=float(p["remaining_days"]),
            start_date=start_date,
            renewal_days=renewal_days,
            _color_index=i,
        )
        projects.append(project)

    return projects


@click.group()
@click.option(
    "-c", "--config",
    default=DEFAULT_CONFIG_FILE,
    help=f"Path to configuration file (default: {DEFAULT_CONFIG_FILE})",
    show_default=True,
)
@click.pass_context
def cli(ctx, config):
    """A minimalist project planner with GitHub-style tile visualization."""
    ctx.ensure_object(dict)
    ctx.obj['config'] = config


@cli.command()
@click.option(
    "-w", "--weeks",
    type=int,
    default=52,
    help="Number of weeks to plan ahead",
    show_default=True,
)
@click.option(
    "-m", "--method",
    type=click.Choice(["paced", "frontload"], case_sensitive=False),
    default="paced",
    help="Scheduling method: 'paced' (balanced) or 'frontload' (concentrated)",
    show_default=True,
)
@click.pass_context
def plan(ctx, weeks, method):
    """Generate and display project schedule."""
    config_path = ctx.obj['config']

    with console.status("[bold green]Loading projects...", spinner="dots"):
        projects = load_projects(config_path)

    if not projects:
        console.print("[yellow]No projects found in configuration file.[/yellow]")
        return

    # Show project summary
    table = Table(title=f"Planning {len(projects)} projects", box=box.ROUNDED)
    table.add_column("Project", style="cyan", no_wrap=True)
    table.add_column("End Date", style="magenta")
    table.add_column("Remaining Days", justify="right", style="green")

    for project in projects:
        table.add_row(
            project.name,
            project.end_date.strftime("%Y-%m-%d"),
            f"{project.remaining_days:.1f}"
        )

    console.print(table)
    console.print()

    # Create scheduler
    with console.status("[bold green]Generating schedules...", spinner="dots"):
        scheduler = Scheduler(projects, start_date=date.today())
        schedule_paced = scheduler.create_schedule(num_weeks=weeks, method="paced")
        schedule_frontload = scheduler.create_schedule(num_weeks=weeks, method="frontload")

    # Determine which schedule to show tiles for
    selected_method = method.lower()
    selected_schedule = schedule_paced if selected_method == "paced" else schedule_frontload

    # Display tile visualization for selected method only
    console.print(Panel(
        f"[bold]Schedule Visualization[/bold]\n[dim]Method: {selected_method.upper()}[/dim]",
        border_style="blue",
        box=box.DOUBLE
    ))
    console.print()
    console.print(render_tiles(selected_schedule))
    console.print()

    # Compute weekly availability for both methods
    paced_availability = compute_weekly_availability(schedule_paced, weeks)
    frontload_availability = compute_weekly_availability(schedule_frontload, weeks)

    # Display availability plot
    console.print(render_availability_plot(paced_availability, frontload_availability))
    console.print()

    # Display statistics for both methods
    stats_paced = scheduler.get_statistics(schedule_paced)
    stats_frontload = scheduler.get_statistics(schedule_frontload)

    console.print(Panel(
        "[bold]Statistics Comparison[/bold]",
        border_style="blue",
        box=box.DOUBLE
    ))
    console.print()

    console.print("[bold cyan]PACED METHOD[/bold cyan] (default)")
    console.print(render_statistics(stats_paced, schedule_paced))
    console.print()

    console.print("[bold yellow]FRONTLOAD METHOD[/bold yellow]")
    console.print(render_statistics(stats_frontload, schedule_frontload))


@cli.command()
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing configuration file",
)
@click.pass_context
def init(ctx, force):
    """Initialize a sample configuration file."""
    config_path = Path(ctx.obj['config'])

    if config_path.exists() and not force:
        console.print(f"[yellow]Configuration file '{ctx.obj['config']}' already exists.[/yellow]")
        console.print("[dim]Use --force to overwrite.[/dim]")
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

    console.print(f"[green]Created sample configuration file:[/green] {ctx.obj['config']}")
    console.print("[dim]Edit this file to add your projects, then run 'planner plan'[/dim]")


@cli.command(name="import")
@click.argument("excel_file", type=click.Path(exists=True))
@click.option(
    "--import-config",
    default=DEFAULT_IMPORT_CONFIG_FILE,
    help=f"Path to import configuration file",
    show_default=True,
)
@click.pass_context
def import_cmd(ctx, excel_file, import_config):
    """Import or update projects from an Excel file."""
    try:
        # Load import configuration
        with console.status("[bold green]Loading import configuration...", spinner="dots"):
            config = load_import_config(import_config)

        console.print(f"[cyan]Reading Excel file:[/cyan] {excel_file}")
        console.print(f"[cyan]Using import config:[/cyan] {import_config}")
        console.print()

        # Read projects from Excel
        with console.status("[bold green]Reading Excel data...", spinner="dots"):
            new_projects = read_excel_projects(excel_file, config)

        console.print(f"[green]Found {len(new_projects)} projects in Excel file[/green]")
        console.print()

        # Update projects.json
        with console.status("[bold green]Updating projects...", spinner="dots"):
            stats = update_projects_json(new_projects, ctx.obj['config'])

        # Display results in a table
        table = Table(title="Import Summary", box=box.ROUNDED)
        table.add_column("Status", style="bold")
        table.add_column("Count", justify="right", style="cyan")

        table.add_row("Added", f"[green]{stats['added']}[/green]")
        table.add_row("Updated", f"[yellow]{stats['updated']}[/yellow]")
        table.add_row("Unchanged", f"[dim]{stats['unchanged']}[/dim]")

        console.print(table)
        console.print()
        console.print(f"[green]Projects saved to:[/green] {ctx.obj['config']}")

    except ImportError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print()
        console.print("[yellow]To enable Excel import, install openpyxl:[/yellow]")
        console.print("  [cyan]uv pip install openpyxl[/cyan]")
        console.print("  or: [cyan]pip install planner[excel][/cyan]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error during import:[/red] {e}")
        sys.exit(1)


@cli.command()
@click.option(
    "--import-config",
    default=DEFAULT_IMPORT_CONFIG_FILE,
    help=f"Path to import configuration file",
    show_default=True,
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing configuration file",
)
def init_import_config(import_config, force):
    """Initialize a sample import configuration file."""
    config_path = Path(import_config)

    if config_path.exists() and not force:
        console.print(f"[yellow]Import configuration file '{import_config}' already exists.[/yellow]")
        console.print("[dim]Use --force to overwrite.[/dim]")
        return

    save_default_import_config(import_config)

    console.print(f"[green]Created sample import configuration file:[/green] {import_config}")
    console.print("[dim]Edit this file to customize the column mapping for your Excel file.[/dim]")
    console.print()

    # Display configuration details
    info = Table(title="Default Configuration", box=box.SIMPLE)
    info.add_column("Setting", style="cyan", no_wrap=True)
    info.add_column("Value", style="white")

    info.add_row("Sheet", "First sheet (index 0)")
    info.add_row("Header row", "Row 1")
    info.add_row("", "")
    info.add_row("[bold]Column Mapping", "")
    info.add_row("'Project Name'", "→ name")
    info.add_row("'End Date'", "→ end_date")
    info.add_row("'Remaining Days'", "→ remaining_days")
    info.add_row("'Start Date'", "→ start_date (optional)")
    info.add_row("'Renewal Days'", "→ renewal_days (optional)")

    console.print(info)


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point for the CLI."""
    try:
        cli(obj={}, args=argv)
        return 0
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
