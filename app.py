"""Shiny app: interactive project planner.

Run: source .venv/bin/activate && shiny run --reload app.py
"""

from datetime import date

import pandas as pd
from htmltools import HTML
from shiny import App, reactive, render, ui
from shinywidgets import output_widget, render_widget

from planner.analysis import (
    _hsl_to_rgb,
    compute_monthly_unassigned_days,
    compute_weekly_availability,
    create_availability_plot,
    create_calendar_heatmap,
    create_project_allocation_plot,
    load_projects,
)
from planner.scheduler import Scheduler

CONFIG_FILE = "projects.json"
DEFAULT_START = date(2026, 6, 29)
DEFAULT_NUM_WEEKS = 52

ALL_PROJECTS = load_projects(CONFIG_FILE)
ACTIVE = [p for p in ALL_PROJECTS if p.probability >= 1.0]
PENDING = [p for p in ALL_PROJECTS if p.probability < 1.0]


def _stable_color_map(projects) -> dict[str, str]:
    """Stable name -> hex color, including renewals.

    Assigns colors by the project's position in projects.json so toggling a
    project on/off does not reshuffle the palette.
    """
    color_map: dict[str, str] = {}
    n = max(len(projects), 1)
    for i, p in enumerate(projects):
        r, g, b = _hsl_to_rgb((i * 360 / n) % 360, 65, 45)
        color_map[p.name] = f"#{r:02x}{g:02x}{b:02x}"
        color_map[f"{p.name} (Renewal)"] = color_map[p.name]
    return color_map


def _pending_label(p) -> HTML:
    full = f"{p.name} (p={p.probability:g})"
    safe = p.name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return HTML(
        f"<span title='{full}'>{safe} "
        f"<span style='color:var(--planner-muted);font-size:0.82em;'>"
        f"p={p.probability:g}</span></span>"
    )


CUSTOM_CSS = """
:root {
  --planner-accent: #2563eb;
  --planner-muted: #6b7280;
  --planner-border: #e5e7eb;
  --planner-bg-soft: #f9fafb;
}

body, .bslib-page-sidebar {
  font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color: #111827;
}

h1.app-title {
  font-size: 1.6rem;
  font-weight: 600;
  margin: 0;
}
.app-subtitle {
  font-size: 0.9rem;
  color: var(--planner-muted);
  margin-top: 2px;
}
.app-header {
  padding: 16px 20px 12px 20px;
  border-bottom: 1px solid var(--planner-border);
  background: white;
}

.summary-card {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  padding: 12px 16px;
  margin: 16px 0 14px 0;
  background: var(--planner-bg-soft);
  border: 1px solid var(--planner-border);
  border-radius: 8px;
}
.summary-stat { min-width: 110px; }
.summary-stat .label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--planner-muted);
  font-weight: 500;
}
.summary-stat .value {
  font-size: 1.25rem;
  font-weight: 600;
  color: #111827;
}
.summary-stat.danger .value { color: #b91c1c; }
.summary-stat.warn .value { color: #b45309; }

/* Sidebar: independent vertical scroll so long project lists don't push the page */
.bslib-sidebar-layout > .sidebar,
aside.sidebar {
  font-size: 0.9rem;
}
.bslib-sidebar-layout > .sidebar > .sidebar-content,
aside.sidebar .sidebar-content {
  max-height: calc(100vh - 110px);
  overflow-y: auto;
  padding-right: 6px;
}
.sidebar h4 {
  font-size: 0.78rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--planner-muted);
  margin: 8px 0 4px 0;
}
.sidebar hr { margin: 8px 0; }
.sidebar .form-group { margin-bottom: 0.4rem; }

/* Compact checkbox rows with single-line truncation for long pending names */
.sidebar .shiny-input-checkboxgroup .shiny-options-group {
  max-height: none;
}
.sidebar .shiny-input-checkboxgroup label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 400;
  margin-bottom: 1px;
  line-height: 1.2;
  max-width: 100%;
}
.sidebar .shiny-input-checkboxgroup label > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.sidebar .btn-sm {
  padding: 2px 10px;
  font-size: 0.78rem;
}

/* Budget table risk coloring */
.budget-table table { font-size: 0.9rem; }
.budget-table tr.risk-missed td { background: #fef2f2; }
.budget-table tr.risk-tight   td { background: #fffbeb; }
.budget-table td.col-days-before { font-weight: 600; }
.budget-table td.col-days-before.missed { color: #b91c1c; }
.budget-table td.col-days-before.tight  { color: #b45309; }

/* Tab polish */
.nav-tabs .nav-link {
  font-weight: 500;
  color: #374151;
}
.nav-tabs .nav-link.active {
  color: var(--planner-accent);
  border-bottom: 2px solid var(--planner-accent);
}
"""


app_ui = ui.page_fluid(
    ui.tags.head(
        ui.tags.link(
            rel="stylesheet",
            href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
        ),
        ui.tags.style(CUSTOM_CSS),
    ),
    ui.div(
        ui.h1("Project Planner", class_="app-title"),
        ui.div(
            "Toggle projects to recompute paced and frontload schedules in real time.",
            class_="app-subtitle",
        ),
        class_="app-header",
    ),
    ui.layout_sidebar(
        ui.sidebar(
            ui.h4("Horizon"),
            ui.input_date("start_date", "Start date", value=DEFAULT_START),
            ui.input_slider(
                "num_weeks",
                "Horizon (weeks)",
                min=12,
                max=208,
                value=DEFAULT_NUM_WEEKS,
                step=4,
            ),
            ui.hr(),
            ui.input_action_button(
                "refresh_projects",
                "Refresh projects",
                class_="btn-sm btn-outline-primary",
                style="margin-bottom:8px;",
            ),
            ui.h4("Active projects"),
            ui.div(
                ui.input_action_button(
                    "active_all", "All", class_="btn-sm btn-outline-secondary"
                ),
                ui.input_action_button(
                    "active_none", "None", class_="btn-sm btn-outline-secondary"
                ),
                style="display:flex; gap:6px; margin-bottom:6px;",
            ),
            ui.input_checkbox_group(
                "active_selected",
                label=None,
                choices={p.name: p.name for p in ACTIVE},
                selected=[p.name for p in ACTIVE],
            ),
            ui.hr(),
            ui.h4("Pending projects"),
            ui.div(
                ui.input_action_button(
                    "pending_all", "All", class_="btn-sm btn-outline-secondary"
                ),
                ui.input_action_button(
                    "pending_none", "None", class_="btn-sm btn-outline-secondary"
                ),
                style="display:flex; gap:6px; margin-bottom:6px;",
            ),
            ui.input_checkbox_group(
                "pending_selected",
                label=None,
                choices={p.name: _pending_label(p) for p in PENDING},
                selected=[],
            ),
            width=320,
        ),
        ui.output_ui("summary_card"),
        ui.navset_tab(
            ui.nav_panel(
                "Overview",
                output_widget("overview_calendar"),
                ui.div(style="height:12px;"),
                output_widget("overview_availability"),
            ),
            ui.nav_panel(
                "Paced",
                output_widget("paced_calendar"),
                ui.h4("Unassigned days"),
                ui.output_data_frame("paced_unassigned"),
            ),
            ui.nav_panel(
                "Frontload",
                output_widget("frontload_calendar"),
                ui.h4("Unassigned days"),
                ui.output_data_frame("frontload_unassigned"),
            ),
            ui.nav_panel("Allocation", output_widget("allocation_plot")),
            ui.nav_panel(
                "Budget",
                ui.h4("Paced"),
                ui.output_ui("paced_budget"),
                ui.h4("Frontload"),
                ui.output_ui("frontload_budget"),
            ),
        ),
    ),
    title="Project Planner",
)


def server(input, output, session):
    projects_state = reactive.value(
        {
            "all": ALL_PROJECTS,
            "active": ACTIVE,
            "pending": PENDING,
            "color_map": _stable_color_map(ALL_PROJECTS),
        }
    )

    @reactive.effect
    @reactive.event(input.refresh_projects)
    def _refresh():
        prev_active_names = {p.name for p in projects_state.get()["active"]}
        all_projects = load_projects(CONFIG_FILE)
        active = [p for p in all_projects if p.probability >= 1.0]
        pending = [p for p in all_projects if p.probability < 1.0]
        projects_state.set(
            {
                "all": all_projects,
                "active": active,
                "pending": pending,
                "color_map": _stable_color_map(all_projects),
            }
        )
        active_names = {p.name for p in active}
        pending_names = {p.name for p in pending}
        kept_active = [n for n in input.active_selected() if n in active_names]
        added_active = [p.name for p in active if p.name not in prev_active_names]
        kept_pending = [n for n in input.pending_selected() if n in pending_names]
        ui.update_checkbox_group(
            "active_selected",
            choices={p.name: p.name for p in active},
            selected=kept_active + added_active,
        )
        ui.update_checkbox_group(
            "pending_selected",
            choices={p.name: _pending_label(p) for p in pending},
            selected=kept_pending,
        )
        ui.notification_show(
            f"Reloaded {len(all_projects)} projects from {CONFIG_FILE}",
            type="message",
            duration=3,
        )

    @reactive.effect
    @reactive.event(input.active_all)
    def _():
        ui.update_checkbox_group(
            "active_selected",
            selected=[p.name for p in projects_state.get()["active"]],
        )

    @reactive.effect
    @reactive.event(input.active_none)
    def _():
        ui.update_checkbox_group("active_selected", selected=[])

    @reactive.effect
    @reactive.event(input.pending_all)
    def _():
        ui.update_checkbox_group(
            "pending_selected",
            selected=[p.name for p in projects_state.get()["pending"]],
        )

    @reactive.effect
    @reactive.event(input.pending_none)
    def _():
        ui.update_checkbox_group("pending_selected", selected=[])

    @reactive.calc
    def selected_projects():
        names = set(input.active_selected()) | set(input.pending_selected())
        return [p for p in projects_state.get()["all"] if p.name in names]

    @reactive.calc
    def schedule_paced():
        projects = selected_projects()
        if not projects:
            return None
        sched = Scheduler(projects, start_date=input.start_date())
        return sched, sched.create_schedule(num_weeks=input.num_weeks(), method="paced")

    @reactive.calc
    def schedule_frontload():
        projects = selected_projects()
        if not projects:
            return None
        sched = Scheduler(projects, start_date=input.start_date())
        return sched, sched.create_schedule(
            num_weeks=input.num_weeks(), method="frontload"
        )

    def _empty_fig(msg: str):
        import plotly.graph_objects as go

        fig = go.Figure()
        fig.add_annotation(
            text=msg,
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font=dict(size=14, color="#6b7280"),
        )
        fig.update_layout(
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            plot_bgcolor="white",
            paper_bgcolor="white",
            height=300,
        )
        return fig

    @render.ui
    def summary_card():
        projects = selected_projects()
        n_active = len(input.active_selected())
        n_pending = len(input.pending_selected())
        total_days = sum(p.remaining_days for p in projects)

        # Count at-risk projects against the paced schedule
        at_risk = 0
        missed = 0
        result = schedule_paced()
        if result is not None:
            scheduler, sched = result
            for project in scheduler.projects:
                budget = project.slots_remaining
                if budget <= 0:
                    continue
                dates = sorted(s.date for s in sched.slots if s.project == project)
                if len(dates) < budget:
                    missed += 1
                else:
                    if (project.end_date - dates[budget - 1]).days < 14:
                        at_risk += 1

        def stat(label: str, value: str, cls: str = "") -> ui.Tag:
            return ui.div(
                ui.div(label, class_="label"),
                ui.div(value, class_="value"),
                class_=f"summary-stat {cls}",
            )

        return ui.div(
            stat("Active", str(n_active)),
            stat("Pending", str(n_pending)),
            stat("Total days", f"{total_days:g}"),
            stat("Tight (<14d buffer)", str(at_risk), "warn" if at_risk else ""),
            stat("Missed deadline", str(missed), "danger" if missed else ""),
            class_="summary-card",
        )

    # ----- Overview tab -----
    @render_widget
    def overview_calendar():
        result = schedule_paced()
        if result is None:
            return _empty_fig("No projects selected")
        return create_calendar_heatmap(
            result[1], "Paced Method Calendar", projects_state.get()["color_map"]
        ) or _empty_fig("No data")

    @render_widget
    def overview_availability():
        paced_result = schedule_paced()
        frontload_result = schedule_frontload()
        if paced_result is None or frontload_result is None:
            return _empty_fig("No projects selected")
        nw = input.num_weeks()
        return create_availability_plot(
            compute_weekly_availability(paced_result[1], nw),
            compute_weekly_availability(frontload_result[1], nw),
        )

    # ----- Paced / Frontload calendar tabs -----
    @render_widget
    def paced_calendar():
        result = schedule_paced()
        if result is None:
            return _empty_fig("No projects selected")
        return create_calendar_heatmap(
            result[1], "Paced Method Calendar", projects_state.get()["color_map"]
        ) or _empty_fig("No data")

    @render_widget
    def frontload_calendar():
        result = schedule_frontload()
        if result is None:
            return _empty_fig("No projects selected")
        return create_calendar_heatmap(
            result[1], "Frontload Method Calendar", projects_state.get()["color_map"]
        ) or _empty_fig("No data")

    @render_widget
    def allocation_plot():
        result = schedule_paced()
        if result is None:
            return _empty_fig("No projects selected")
        return create_project_allocation_plot(
            result[1], input.num_weeks(), projects_state.get()["color_map"]
        ) or _empty_fig("No data")

    def _unassigned_df(sched):
        df = compute_monthly_unassigned_days(sched, include_zero_months=True)
        if df.empty:
            return pd.DataFrame(columns=["Month", "Unassigned Days", "Cumulative"])
        df = df.copy()
        df["cumulative"] = df["unassigned_days"].cumsum()
        return df[["month_name", "unassigned_days", "cumulative"]].rename(
            columns={
                "month_name": "Month",
                "unassigned_days": "Unassigned Days",
                "cumulative": "Cumulative",
            }
        )

    @render.data_frame
    def paced_unassigned():
        result = schedule_paced()
        if result is None:
            return pd.DataFrame()
        return _unassigned_df(result[1])

    @render.data_frame
    def frontload_unassigned():
        result = schedule_frontload()
        if result is None:
            return pd.DataFrame()
        return _unassigned_df(result[1])

    # ----- Budget table with risk coloring -----
    def _budget_rows(sched, projects):
        rows = []
        for project in projects:
            budget = project.slots_remaining
            if budget <= 0:
                continue
            dates = sorted(s.date for s in sched.slots if s.project == project)
            scheduled = len(dates)
            exhausted = dates[budget - 1] if scheduled >= budget else None
            days_before = (project.end_date - exhausted).days if exhausted else None
            rows.append(
                {
                    "project": project.name,
                    "end_date": project.end_date,
                    "budget": budget,
                    "scheduled": scheduled,
                    "exhausted": exhausted,
                    "days_before": days_before,
                }
            )
        rows.sort(key=lambda r: (r["end_date"], r["project"]))
        return rows

    def _budget_html(rows) -> HTML:
        if not rows:
            return HTML("<p style='color:var(--planner-muted);'>No projects.</p>")
        out = [
            "<table class='table table-sm budget-table'>",
            "<thead><tr>",
            "<th>Project</th><th>End Date</th>",
            "<th style='text-align:right;'>Budget</th>",
            "<th style='text-align:right;'>Scheduled</th>",
            "<th>Exhausted On</th>",
            "<th style='text-align:right;'>Days Before Deadline</th>",
            "</tr></thead><tbody>",
        ]
        for r in rows:
            risk_cls = ""
            days_cell_cls = "col-days-before"
            days_val = "—"
            if r["days_before"] is None:
                risk_cls = "risk-missed"
                days_cell_cls += " missed"
                days_val = f"not exhausted ({r['scheduled']}/{r['budget']})"
            elif r["days_before"] < 0:
                risk_cls = "risk-missed"
                days_cell_cls += " missed"
                days_val = f"{r['days_before']} (late)"
            elif r["days_before"] < 14:
                risk_cls = "risk-tight"
                days_cell_cls += " tight"
                days_val = str(r["days_before"])
            else:
                days_val = str(r["days_before"])

            out.append(f"<tr class='{risk_cls}'>")
            out.append(f"<td>{r['project']}</td>")
            out.append(f"<td>{r['end_date']}</td>")
            out.append(f"<td style='text-align:right;'>{r['budget']}</td>")
            out.append(f"<td style='text-align:right;'>{r['scheduled']}</td>")
            out.append(f"<td>{r['exhausted'] if r['exhausted'] else '—'}</td>")
            out.append(
                f"<td class='{days_cell_cls}' style='text-align:right;'>{days_val}</td>"
            )
            out.append("</tr>")
        out.append("</tbody></table>")
        return HTML("".join(out))

    @render.ui
    def paced_budget():
        result = schedule_paced()
        if result is None:
            return HTML("<p>No projects selected.</p>")
        scheduler, sched = result
        return _budget_html(_budget_rows(sched, scheduler.projects))

    @render.ui
    def frontload_budget():
        result = schedule_frontload()
        if result is None:
            return HTML("<p>No projects selected.</p>")
        scheduler, sched = result
        return _budget_html(_budget_rows(sched, scheduler.projects))


app = App(app_ui, server)
