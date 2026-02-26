#!/usr/bin/env python3
"""
extract_cpos_projects.py
────────────────────────
Extract pending projects from the most recent CPOS PDF and update projects.json.

Logic:
  1. Find the most recent cpos*.pdf file in the root folder
  2. Parse pending projects from the PDF
  3. Calculate remaining_days = 226 * (first year person months) / 12
  4. Update projects.json:
     - Add new pending projects with probability=0.5
     - Remove pending projects that are no longer in the CPOS
     - Keep all active projects (without probability field)
     - Keep pending projects that match titles in CPOS
  5. Save Excel file with same name as PDF

Usage:
    python -m osparse.extract_cpos_projects
    or
    python osparse/extract_cpos_projects.py
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import Workbook

from .parse_cpos import (
    extract_lines,
    parse_projects,
    write_person_months_sheet,
    write_projects_sheet,
)


def find_most_recent_cpos_pdf(root_dir: Path) -> Path | None:
    """Find the most recent cpos*.pdf file in the root directory."""
    cpos_files = list(root_dir.glob("cpos*.pdf"))
    if not cpos_files:
        return None
    # Sort by modification time, most recent first
    return max(cpos_files, key=lambda p: p.stat().st_mtime)


def parse_date(date_str: str, default_day: int = 1) -> str | None:
    """
    Parse date string from CPOS format to YYYY-MM-DD.
    Handles formats like: MM/YYYY, MM/DD/YYYY, YYYY-MM-DD, etc.

    For MM/YYYY format, uses default_day (1 for start dates, last day for end dates).
    """
    if not date_str or not date_str.strip():
        return None

    date_str = date_str.strip()

    # Try MM/YYYY format first (common in CPOS forms)
    try:
        dt = datetime.strptime(date_str, "%m/%Y")
        # Use the specified default day
        if default_day == -1:
            # Last day of the month
            if dt.month == 12:
                next_month = datetime(dt.year + 1, 1, 1)
            else:
                next_month = datetime(dt.year, dt.month + 1, 1)
            last_day = next_month - timedelta(days=1)
            return last_day.strftime("%Y-%m-%d")
        else:
            return datetime(dt.year, dt.month, default_day).strftime("%Y-%m-%d")
    except ValueError:
        pass

    # Try other common formats with full dates
    for fmt in ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%Y/%m/%d"]:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def calculate_remaining_days(person_months: list[dict], start_date_str: str) -> float:
    """
    Calculate remaining days from first year person months.
    Formula: 226 * (person_months in first year) / 12

    Args:
        person_months: List of {year: int, months: float} dicts
        start_date_str: Start date string in YYYY-MM-DD format

    Returns:
        Remaining days (float)

    Note:
        Uses the earliest year with person months allocated, which may differ
        from the start_date year (e.g., project starts Dec 2026 but work begins in 2027).
    """
    if not person_months:
        return 0.0

    try:
        # Find the first year with person months allocated
        years_with_work = sorted([pm["year"] for pm in person_months])
        if not years_with_work:
            return 0.0

        first_year_with_work = years_with_work[0]

        # Sum person months for the first year of actual work
        first_year_months = sum(
            pm["months"] for pm in person_months if pm["year"] == first_year_with_work
        )

        # Calculate remaining days
        return round(226 * first_year_months / 12, 1)
    except (ValueError, KeyError):
        return 0.0


def normalize_title(title: str) -> str:
    """
    Normalize project title for comparison.
    Removes extra whitespace, converts to lowercase.
    """
    return re.sub(r"\s+", " ", title.lower().strip())


def load_projects_json(json_path: Path) -> dict:
    """Load projects.json file."""
    if not json_path.exists():
        return {"projects": []}

    with open(json_path, "r") as f:
        return json.load(f)


def save_projects_json(json_path: Path, data: dict):
    """Save projects.json file with proper formatting."""
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")  # Add trailing newline


def extract_pending_projects_from_cpos(cpos_projects: list[dict]) -> list[dict]:
    """
    Extract pending projects from parsed CPOS data.

    Returns list of dicts with:
        - name: project title
        - start_date: YYYY-MM-DD (first day of start month)
        - end_date: YYYY-MM-DD (first year only, last day of end month)
        - remaining_days: calculated from person months
    """
    pending = []

    for proj in cpos_projects:
        # Only process pending projects
        if proj["status"].lower() != "pending":
            continue

        # Parse start date (use first day of month)
        start_date = parse_date(proj["start"], default_day=1)
        # Parse end date (use last day of month)
        end_date = parse_date(proj["end"], default_day=-1)

        if not start_date:
            print(f"  Warning: Skipping project '{proj['title'][:50]}' - missing start date")
            continue

        # If end_date is missing, try to infer from person months
        if not end_date and proj["person_months"]:
            # Use the last year with person months to infer end date
            years = [pm["year"] for pm in proj["person_months"]]
            if years:
                last_year = max(years)
                # Assume project ends in December of the last year with person months
                end_date = f"{last_year}-12-31"
                print(f"  Info: Inferred end date {end_date} from person months for '{proj['title'][:50]}'")

        if not end_date:
            print(f"  Warning: Skipping project '{proj['title'][:50]}' - missing end date and no person months to infer from")
            continue

        # Calculate end date for first year only
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        # Use the earlier of: actual end date or one year from start (minus 1 day)
        first_year_end_dt = datetime(start_dt.year + 1, start_dt.month, start_dt.day) - timedelta(days=1)
        if end_dt < first_year_end_dt:
            first_year_end = end_date
        else:
            first_year_end = first_year_end_dt.strftime("%Y-%m-%d")

        # Calculate remaining days from person months
        remaining_days = calculate_remaining_days(proj["person_months"], start_date)

        if remaining_days == 0:
            print(f"  Warning: Project '{proj['title'][:50]}' has 0 remaining days")

        pending.append({
            "name": proj["title"],
            "start_date": start_date,
            "end_date": first_year_end,
            "remaining_days": remaining_days,
        })

    return pending


def update_projects_json(
    json_path: Path,
    cpos_pending: list[dict],
    default_probability: float = 0.5
):
    """
    Update projects.json with pending projects from CPOS.

    Logic:
      - Keep all active projects (no probability field)
      - Remove pending projects not in CPOS
      - Keep pending projects that match CPOS titles
      - Add new pending projects with default probability
    """
    data = load_projects_json(json_path)
    existing_projects = data.get("projects", [])

    # Build lookup of CPOS pending projects by normalized title
    cpos_by_title = {
        normalize_title(p["name"]): p for p in cpos_pending
    }

    # Build lookup of existing pending projects by normalized title
    existing_pending_by_title = {
        normalize_title(p["name"]): p
        for p in existing_projects
        if "probability" in p
    }

    # Step 1: Keep all active projects (no probability field)
    active_projects = [p for p in existing_projects if "probability" not in p]

    # Step 2: Update pending projects that match CPOS titles (preserve probability but update dates/days)
    matched_pending = []
    for norm_title, existing_proj in existing_pending_by_title.items():
        if norm_title in cpos_by_title:
            cpos_proj = cpos_by_title[norm_title]
            # Preserve existing probability and priority, but update other fields from CPOS
            updated_proj = cpos_proj.copy()
            updated_proj["probability"] = existing_proj.get("probability", default_probability)
            if "priority" in existing_proj:
                updated_proj["priority"] = existing_proj["priority"]
            matched_pending.append(updated_proj)

    # Step 3: Add new pending projects from CPOS
    new_pending = []
    for norm_title, cpos_proj in cpos_by_title.items():
        if norm_title not in existing_pending_by_title:
            # This is a new pending project
            new_proj = cpos_proj.copy()
            new_proj["probability"] = default_probability
            new_pending.append(new_proj)

    # Combine: active + matched pending + new pending
    updated_projects = active_projects + matched_pending + new_pending

    # Update and save
    data["projects"] = updated_projects
    save_projects_json(json_path, data)

    # Print summary
    print(f"\nProjects.json update summary:")
    print(f"  Active projects (kept):     {len(active_projects)}")
    print(f"  Matched pending (kept):     {len(matched_pending)}")
    print(f"  New pending (added):        {len(new_pending)}")
    removed_count = len(existing_pending_by_title) - len(matched_pending)
    if removed_count > 0:
        print(f"  Pending projects (removed): {removed_count}")


def main():
    """Main entry point."""
    # Find root directory (parent of osparse folder)
    script_dir = Path(__file__).parent
    root_dir = script_dir.parent

    print("="*70)
    print("CPOS Pending Projects Extraction")
    print("="*70)

    # Find most recent CPOS PDF
    cpos_pdf = find_most_recent_cpos_pdf(root_dir)
    if not cpos_pdf:
        print("Error: No cpos*.pdf file found in root directory")
        return 1

    print(f"\nFound CPOS PDF: {cpos_pdf.name}")

    # Parse CPOS PDF
    print(f"Parsing {cpos_pdf} ...")
    lines = extract_lines(str(cpos_pdf))
    all_projects = parse_projects(lines)
    print(f"  Found {len(all_projects)} total projects in CPOS")

    # Extract pending projects
    pending_projects = extract_pending_projects_from_cpos(all_projects)
    print(f"  Extracted {len(pending_projects)} pending projects")

    if pending_projects:
        print("\nPending projects:")
        for p in pending_projects:
            print(f"  - {p['name'][:60]}")
            print(f"    Dates: {p['start_date']} to {p['end_date']}")
            print(f"    Remaining days: {p['remaining_days']}")

    # Update projects.json
    json_path = root_dir / "projects.json"
    print(f"\nUpdating {json_path.name} ...")
    update_projects_json(json_path, pending_projects)

    # Save Excel file
    xlsx_path = cpos_pdf.with_suffix(".xlsx")
    print(f"\nSaving Excel file: {xlsx_path.name} ...")
    wb = Workbook()
    write_projects_sheet(wb.active, all_projects)
    write_person_months_sheet(wb.create_sheet(), all_projects)
    wb.save(str(xlsx_path))
    print(f"  Saved → {xlsx_path}")

    print("\n" + "="*70)
    print("Done!")
    print("="*70)

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
