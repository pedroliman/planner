# osparse - NIH Other Support Form Parser

Tools for parsing NIH Current and Pending (Other) Support PDFs and integrating with the project planner.

## Overview

This package contains two main tools:

1. **parse_cpos.py** - Parse CPOS PDFs and generate Excel reports
2. **extract_cpos_projects.py** - Extract pending projects and update projects.json

## Usage

### Extract Pending Projects (Primary Tool)

This is the main tool for updating your `projects.json` from CPOS forms:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the extraction tool
python -m osparse.extract_cpos_projects
```

**What it does:**
1. Finds the most recent `cpos*.pdf` file in the root directory
2. Parses all projects from the PDF
3. Extracts pending projects (status = "Pending")
4. Calculates `remaining_days = 226 * (first year person months) / 12`
5. Updates `projects.json`:
   - Keeps all active projects (no `probability` field)
   - Updates existing pending projects (preserves their `probability` value)
   - Adds new pending projects with `probability: 0.5`
   - Removes pending projects not in the CPOS
6. Saves Excel file with the same name as the PDF

**Project fields extracted:**
- `name`: Project title from CPOS
- `start_date`: First day of start month (YYYY-MM-DD)
- `end_date`: Last day of first year (YYYY-MM-DD)
- `remaining_days`: Calculated from person months
- `probability`: 0.5 for new projects, preserved for existing projects

### Parse CPOS Only (Generate Excel)

If you just want to parse a CPOS PDF and generate an Excel file:

```bash
python osparse/parse_cpos.py cpos-2189507.pdf [output.xlsx]
```

This generates two sheets:
1. **Projects** - All project metadata (title, status, dates, amounts, etc.)
2. **Person Months by Year** - Pivoted table with years as columns

## Date Handling

The parser handles both date formats commonly found in CPOS forms:
- `MM/YYYY` - Converted to first day (start) or last day (end) of month
- `MM/DD/YYYY` - Converted to exact date

## Remaining Days Calculation

Formula: `remaining_days = 226 * (person_months_first_year) / 12`

Where:
- 226 = working days per year (approximate)
- person_months_first_year = sum of person months in the first year of work

**Note:** The script uses the first year with person months allocated, which may differ from the start date year (e.g., project starts Dec 2026 but work begins in 2027).

## Example Output

```
======================================================================
CPOS Pending Projects Extraction
======================================================================

Found CPOS PDF: cpos-2189507.pdf
Parsing /Users/plima/dev/pocs/planner/cpos-2189507.pdf ...
  Found 13 total projects in CPOS
  Extracted 6 pending projects

Pending projects:
  - Comparative Modeling to Inform Colorectal Cancer Control Pol
    Dates: 2026-12-01 to 2027-11-30
    Remaining days: 44.8
  - Methods for Microsimulation Model Calibration
    Dates: 2026-01-01 to 2026-12-31
    Remaining days: 27.7

Updating projects.json ...

Projects.json update summary:
  Active projects (kept):     9
  Matched pending (kept):     6
  New pending (added):        0

Saving Excel file: cpos-2189507.xlsx ...
  Saved → /Users/plima/dev/pocs/planner/cpos-2189507.xlsx

======================================================================
Done!
======================================================================
```

## Dependencies

- `pdfplumber` - PDF text extraction
- `openpyxl` - Excel file generation

Install with: `uv add pdfplumber openpyxl`

## Files

- `__init__.py` - Package initialization
- `parse_cpos.py` - Core CPOS parsing logic
- `extract_cpos_projects.py` - Main extraction tool for projects.json
- `README.md` - This file
