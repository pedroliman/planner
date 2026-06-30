"""Streamlit app: interactive project planner.

Run: source .venv/bin/activate && streamlit run app.py
"""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

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
DEFAULT_START = date(2026, 5, 4)
DEFAULT_NUM_WEEKS = 104

# ---- Editorial palette --------------------------------------------------
INK = "#1a1612"
INK_SOFT = "#3d352c"
MUTED = "#6b6358"
PAPER = "#f6f1e7"
PAPER_2 = "#ede5d3"
RULE = "#d4cabe"
ACCENT = "#c1440e"      # terracotta
WARN = "#b07215"        # amber
DANGER = "#8a1a1a"      # crimson


@st.cache_data
def _load_all_projects():
    return load_projects(CONFIG_FILE)


def _stable_color_map(all_projects) -> dict[str, str]:
    """Stable name -> hex color, including renewals."""
    color_map: dict[str, str] = {}
    n = max(len(all_projects), 1)
    for i, p in enumerate(all_projects):
        # Slightly desaturate to play nicely with the warm paper background
        r, g, b = _hsl_to_rgb((i * 360 / n) % 360, 55, 42)
        color_map[p.name] = f"#{r:02x}{g:02x}{b:02x}"
        color_map[f"{p.name} (Renewal)"] = color_map[p.name]
    return color_map


CUSTOM_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,500;9..144,600;9..144,700&family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {{
  --ink: {INK};
  --ink-soft: {INK_SOFT};
  --muted: {MUTED};
  --paper: {PAPER};
  --paper-2: {PAPER_2};
  --rule: {RULE};
  --accent: {ACCENT};
  --warn: {WARN};
  --danger: {DANGER};
  --serif: 'Fraunces', 'Iowan Old Style', 'Palatino', Georgia, serif;
  --sans: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  --mono: 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace;
}}

/* ---------- Global page ---------- */
html, body {{ font-family: var(--sans); color: var(--ink); }}
.stApp, .stApp p, .stApp span:not([class*="material"]):not([class*="icon"]),
.stApp div, .stApp label {{ font-family: var(--sans); }}
/* Don't touch Streamlit's icon fonts (sidebar collapse, etc) */
[class*="material-icons"], [class*="MaterialIcons"], .st-emotion-cache-icon {{
  font-family: 'Material Symbols Rounded', 'Material Icons' !important;
}}
.stApp {{
  background:
    radial-gradient(circle at 18% 0%, rgba(193, 68, 14, 0.04) 0, transparent 40%),
    radial-gradient(circle at 95% 8%, rgba(26, 22, 18, 0.04) 0, transparent 35%),
    var(--paper);
}}
.block-container {{ padding-top: 1.6rem; padding-bottom: 4rem; max-width: 1380px; }}
::selection {{ background: var(--accent); color: var(--paper); }}

/* Hide streamlit chrome we don't want */
header[data-testid="stHeader"] {{ background: transparent; }}
#MainMenu, footer {{ visibility: hidden; }}

/* ---------- Masthead ---------- */
.masthead {{
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  border-bottom: 1px solid var(--ink);
  padding-bottom: 18px;
  margin-bottom: 22px;
  position: relative;
}}
.masthead::before {{
  content: "";
  position: absolute;
  left: 0; right: 0; bottom: -3px;
  height: 1px;
  background: var(--ink);
}}
.eyebrow {{
  font-family: var(--mono);
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.22em;
  color: var(--accent);
  font-weight: 500;
  display: block;
  margin-bottom: 6px;
}}
.masthead-title {{
  font-family: var(--serif);
  font-variation-settings: "opsz" 144;
  font-weight: 500;
  font-size: 3.2rem;
  line-height: 0.95;
  letter-spacing: -0.025em;
  color: var(--ink);
  margin: 0;
}}
.masthead-title em {{
  font-style: italic;
  font-weight: 400;
  color: var(--accent);
}}
.masthead-meta {{
  font-family: var(--mono);
  font-size: 0.74rem;
  color: var(--muted);
  text-align: right;
  line-height: 1.6;
  letter-spacing: 0.04em;
}}
.masthead-meta b {{ color: var(--ink); font-weight: 500; }}

/* ---------- Hero stats ---------- */
.stats {{
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 0;
  margin: 4px 0 28px 0;
  border-top: 1px solid var(--rule);
  border-bottom: 1px solid var(--rule);
}}
.stat {{
  padding: 18px 20px 16px 20px;
  border-right: 1px solid var(--rule);
  position: relative;
}}
.stat:last-child {{ border-right: none; }}
.stat .label {{
  font-family: var(--mono);
  font-size: 0.66rem;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: var(--muted);
  font-weight: 500;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}}
.stat .label::before {{
  content: "";
  width: 6px; height: 6px;
  background: var(--ink);
  border-radius: 50%;
  display: inline-block;
}}
.stat.warn .label::before {{ background: var(--warn); }}
.stat.danger .label::before {{ background: var(--danger); }}
.stat .value {{
  font-family: var(--serif);
  font-variation-settings: "opsz" 144;
  font-size: 2.4rem;
  font-weight: 400;
  line-height: 1;
  letter-spacing: -0.02em;
  color: var(--ink);
  font-feature-settings: "tnum" 1, "lnum" 1;
}}
.stat .sub {{
  font-family: var(--mono);
  font-size: 0.7rem;
  color: var(--muted);
  margin-top: 6px;
  letter-spacing: 0.02em;
}}
.stat.warn .value {{ color: var(--warn); }}
.stat.danger .value {{ color: var(--danger); }}

/* ---------- Sidebar ---------- */
section[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, var(--paper) 0%, var(--paper-2) 100%);
  border-right: 1px solid var(--rule);
}}
section[data-testid="stSidebar"] > div:first-child {{ padding-top: 1rem; }}
section[data-testid="stSidebar"] .section-head {{
  font-family: var(--mono);
  font-size: 0.66rem;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  color: var(--muted);
  font-weight: 500;
  margin: 18px 0 8px 0;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--rule);
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}}
section[data-testid="stSidebar"] .section-head .count {{
  font-family: var(--mono);
  font-size: 0.68rem;
  color: var(--ink);
  letter-spacing: 0.04em;
  font-feature-settings: "tnum" 1;
}}

/* Sidebar inputs */
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stCheckbox label p {{
  font-family: var(--sans);
  font-size: 0.84rem;
  color: var(--ink);
}}
section[data-testid="stSidebar"] .stCheckbox {{ margin-bottom: -4px; }}
section[data-testid="stSidebar"] .stCheckbox label p {{ line-height: 1.25; }}

/* Date / slider polish */
section[data-testid="stSidebar"] [data-testid="stDateInput"] input,
section[data-testid="stSidebar"] [data-baseweb="input"] input {{
  font-family: var(--mono);
  font-size: 0.8rem;
  background: var(--paper);
  border: 1px solid var(--rule);
  color: var(--ink);
}}
section[data-testid="stSidebar"] [data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {{
  background: var(--accent) !important;
  border-color: var(--accent) !important;
}}

/* Buttons */
section[data-testid="stSidebar"] .stButton > button {{
  background: transparent;
  border: 1px solid var(--ink);
  border-radius: 0;
  font-family: var(--mono);
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink);
  padding: 4px 10px;
  width: 100%;
  transition: all 120ms ease;
}}
section[data-testid="stSidebar"] .stButton > button:hover {{
  background: var(--ink);
  color: var(--paper);
  border-color: var(--ink);
}}
section[data-testid="stSidebar"] .stButton > button:focus,
section[data-testid="stSidebar"] .stButton > button:focus-visible,
section[data-testid="stSidebar"] .stButton > button:active {{
  background: transparent;
  color: var(--ink);
  border-color: var(--ink);
  box-shadow: none;
  outline: none;
}}
section[data-testid="stSidebar"] .stButton > button:focus:hover {{
  background: var(--ink);
  color: var(--paper);
}}

/* Project chip with color swatch via background pseudo on label */
section[data-testid="stSidebar"] .stCheckbox {{ position: relative; padding-left: 0; }}

/* ---------- Tabs ---------- */
.stTabs [data-baseweb="tab-list"] {{
  gap: 0;
  border-bottom: 1px solid var(--ink);
  background: transparent;
}}
.stTabs [data-baseweb="tab"] {{
  background: transparent;
  border-radius: 0;
  padding: 10px 18px;
  font-family: var(--mono);
  font-size: 0.74rem;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--muted);
  font-weight: 500;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: color 120ms ease, border-color 120ms ease;
}}
.stTabs [data-baseweb="tab"]:hover {{ color: var(--ink); }}
.stTabs [aria-selected="true"] {{
  color: var(--ink) !important;
  border-bottom: 2px solid var(--accent) !important;
  background: transparent !important;
}}
.stTabs [data-baseweb="tab-highlight"] {{ display: none; }}
.stTabs [data-baseweb="tab-panel"] {{ padding-top: 22px; }}

/* ---------- Section title within tab ---------- */
.section-title {{
  font-family: var(--serif);
  font-variation-settings: "opsz" 60;
  font-style: italic;
  font-weight: 400;
  font-size: 1.15rem;
  letter-spacing: -0.01em;
  color: var(--ink);
  margin: 22px 0 10px 0;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--rule);
  display: flex;
  align-items: baseline;
  gap: 10px;
}}
.section-title .num {{
  font-family: var(--mono);
  font-style: normal;
  font-size: 0.66rem;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: var(--accent);
  font-weight: 500;
}}

/* ---------- Plot card frame ---------- */
[data-testid="stPlotlyChart"] {{
  background: rgba(255, 251, 244, 0.55);
  border: 1px solid var(--rule);
  border-radius: 2px;
  padding: 10px 8px 6px 8px;
  margin-bottom: 6px;
  box-shadow: 0 1px 0 rgba(26, 22, 18, 0.04);
}}

/* ---------- Editorial table ---------- */
.budget-table table {{
  width: 100%;
  border-collapse: collapse;
  font-family: var(--sans);
  font-size: 0.86rem;
  color: var(--ink);
  margin-bottom: 18px;
}}
.budget-table th {{
  font-family: var(--mono);
  font-size: 0.66rem;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--muted);
  font-weight: 500;
  text-align: left;
  padding: 10px 12px;
  border-bottom: 1px solid var(--ink);
  background: transparent;
}}
.budget-table td {{
  padding: 9px 12px;
  border-bottom: 1px solid var(--rule);
  font-feature-settings: "tnum" 1, "lnum" 1;
}}
.budget-table tr:hover td {{ background: rgba(193, 68, 14, 0.04); }}
.budget-table tr.risk-missed td {{ background: rgba(138, 26, 26, 0.06); }}
.budget-table tr.risk-tight   td {{ background: rgba(176, 114, 21, 0.06); }}
.budget-table td.col-num {{ font-family: var(--mono); font-size: 0.84rem; }}
.budget-table td.col-date {{ font-family: var(--mono); font-size: 0.8rem; color: var(--ink-soft); }}
.budget-table td.col-days-before {{ font-family: var(--mono); font-weight: 500; }}
.budget-table td.col-days-before.missed {{ color: var(--danger); }}
.budget-table td.col-days-before.tight  {{ color: var(--warn); }}
.budget-table .swatch {{
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  margin-right: 8px;
  vertical-align: middle;
  border: 1px solid rgba(26, 22, 18, 0.15);
}}

/* DataFrame restyle */
[data-testid="stDataFrame"] {{
  background: rgba(255, 251, 244, 0.6);
  border: 1px solid var(--rule);
  border-radius: 2px;
}}
[data-testid="stDataFrame"] [class*="cell"] {{
  font-family: var(--mono);
  font-size: 0.8rem;
}}

.empty-note {{
  padding: 32px;
  text-align: center;
  font-family: var(--serif);
  font-style: italic;
  color: var(--muted);
  border: 1px dashed var(--rule);
  background: rgba(255, 251, 244, 0.4);
}}
</style>
"""


def _restyle_fig(fig):
    """Restyle plotly figures to the editorial palette."""
    if fig is None:
        return None
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans, sans-serif", color=INK_SOFT, size=12),
        title=dict(
            font=dict(family="Fraunces, serif", color=INK, size=16),
            x=0.01, xanchor="left",
        ),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            bordercolor=RULE,
            borderwidth=0,
            font=dict(family="JetBrains Mono, monospace", size=10, color=INK_SOFT),
        ),
        xaxis=dict(
            gridcolor=RULE, zerolinecolor=RULE, linecolor=RULE,
            tickfont=dict(family="JetBrains Mono, monospace", size=10, color=MUTED),
        ),
        yaxis=dict(
            gridcolor=RULE, zerolinecolor=RULE, linecolor=RULE,
            tickfont=dict(family="JetBrains Mono, monospace", size=10, color=MUTED),
        ),
    )
    # Some figures pre-set an axis tickfont; force-update both axes uniformly
    for ax in ("xaxis", "yaxis"):
        if ax in fig.layout:
            fig.layout[ax].tickfont.family = "JetBrains Mono, monospace"
            fig.layout[ax].tickfont.color = MUTED
    return fig


def _empty_fig(msg: str):
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.add_annotation(
        text=f"<i>{msg}</i>", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
        font=dict(family="Fraunces, serif", size=15, color=MUTED),
    )
    fig.update_layout(
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", height=240,
        margin=dict(l=20, r=20, t=20, b=20),
    )
    return fig


@st.cache_data(show_spinner=False)
def _build_schedule(selected_names: tuple[str, ...], start_date: date, num_weeks: int, method: str):
    all_projects = _load_all_projects()
    projects = [p for p in all_projects if p.name in selected_names]
    if not projects:
        return None
    sched = Scheduler(projects, start_date=start_date)
    return sched, sched.create_schedule(num_weeks=num_weeks, method=method)


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


def _budget_html(rows, color_map: dict[str, str]) -> str:
    if not rows:
        return "<div class='empty-note'>No projects to budget.</div>"
    out = [
        "<div class='budget-table'><table>",
        "<thead><tr>",
        "<th>Project</th><th>Deadline</th>",
        "<th style='text-align:right;'>Budget</th>",
        "<th style='text-align:right;'>Scheduled</th>",
        "<th>Exhausted</th>",
        "<th style='text-align:right;'>Days Buffer</th>",
        "</tr></thead><tbody>",
    ]
    for r in rows:
        risk_cls = ""
        days_cell_cls = "col-days-before"
        if r["days_before"] is None:
            risk_cls = "risk-missed"
            days_cell_cls += " missed"
            days_val = f"{r['scheduled']}/{r['budget']}"
        elif r["days_before"] < 0:
            risk_cls = "risk-missed"
            days_cell_cls += " missed"
            days_val = f"{r['days_before']}d late"
        elif r["days_before"] < 14:
            risk_cls = "risk-tight"
            days_cell_cls += " tight"
            days_val = f"{r['days_before']}d"
        else:
            days_val = f"{r['days_before']}d"

        swatch = color_map.get(r["project"], INK)
        out.append(f"<tr class='{risk_cls}'>")
        out.append(
            f"<td><span class='swatch' style='background:{swatch}'></span>{r['project']}</td>"
        )
        out.append(f"<td class='col-date'>{r['end_date']}</td>")
        out.append(f"<td class='col-num' style='text-align:right;'>{r['budget']}</td>")
        out.append(f"<td class='col-num' style='text-align:right;'>{r['scheduled']}</td>")
        out.append(
            f"<td class='col-date'>{r['exhausted'] if r['exhausted'] else '—'}</td>"
        )
        out.append(
            f"<td class='{days_cell_cls}' style='text-align:right;'>{days_val}</td>"
        )
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


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


def _section_title(title: str, num: str) -> str:
    return (
        f"<div class='section-title'><span class='num'>{num}</span>"
        f"<span>{title}</span></div>"
    )


def main():
    st.set_page_config(page_title="Project Planner", layout="wide")
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    all_projects = _load_all_projects()
    active = [p for p in all_projects if p.probability >= 1.0]
    pending = [p for p in all_projects if p.probability < 1.0]
    color_map = _stable_color_map(all_projects)

    # ---- Session state -------------------------------------------------
    if "active_selected" not in st.session_state:
        st.session_state.active_selected = {p.name: True for p in active}
    if "pending_selected" not in st.session_state:
        st.session_state.pending_selected = {p.name: False for p in pending}
    for p in active:
        st.session_state.active_selected.setdefault(p.name, True)
    for p in pending:
        st.session_state.pending_selected.setdefault(p.name, False)

    # ---- Sidebar -------------------------------------------------------
    with st.sidebar:
        st.markdown(
            "<div style='font-family:var(--mono);font-size:0.62rem;"
            "letter-spacing:0.22em;text-transform:uppercase;color:var(--accent);"
            "margin-bottom:6px;'>Controls</div>"
            "<div style='font-family:var(--serif);font-style:italic;font-size:1.5rem;"
            "line-height:1;color:var(--ink);margin-bottom:18px;'>Composition</div>",
            unsafe_allow_html=True,
        )

        st.markdown(
            "<div class='section-head'><span>Horizon</span></div>",
            unsafe_allow_html=True,
        )
        start_date = st.date_input("Start", value=DEFAULT_START, label_visibility="collapsed")
        num_weeks = st.slider(
            "Weeks", min_value=12, max_value=208,
            value=DEFAULT_NUM_WEEKS, step=4, label_visibility="visible",
        )

        n_active_total = len(active)
        n_active_on = sum(
            1 for p in active if st.session_state.active_selected.get(p.name)
        )
        st.markdown(
            f"<div class='section-head'><span>Active</span>"
            f"<span class='count'>{n_active_on:02d} / {n_active_total:02d}</span></div>",
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        if c1.button("All", key="active_all"):
            for p in active:
                st.session_state.active_selected[p.name] = True
            st.rerun()
        if c2.button("None", key="active_none"):
            for p in active:
                st.session_state.active_selected[p.name] = False
            st.rerun()

        for p in active:
            swatch = color_map.get(p.name, INK)
            label = (
                f"<span style='display:inline-block;width:8px;height:8px;border-radius:50%;"
                f"background:{swatch};margin-right:6px;vertical-align:middle;"
                f"border:1px solid rgba(26,22,18,0.15);'></span>{p.name}"
            )
            with st.container():
                st.session_state.active_selected[p.name] = st.checkbox(
                    p.name,
                    value=st.session_state.active_selected.get(p.name, True),
                    key=f"active_{p.name}",
                    label_visibility="collapsed",
                )
                # Render label inline next to checkbox via small CSS hack
                st.markdown(
                    f"<div style='margin:-32px 0 4px 30px;font-size:0.84rem;"
                    f"color:var(--ink);line-height:1.25;'>{label}</div>",
                    unsafe_allow_html=True,
                )

        n_pending_total = len(pending)
        n_pending_on = sum(
            1 for p in pending if st.session_state.pending_selected.get(p.name)
        )
        st.markdown(
            f"<div class='section-head'><span>Pending</span>"
            f"<span class='count'>{n_pending_on:02d} / {n_pending_total:02d}</span></div>",
            unsafe_allow_html=True,
        )
        c3, c4 = st.columns(2)
        if c3.button("All", key="pending_all"):
            for p in pending:
                st.session_state.pending_selected[p.name] = True
            st.rerun()
        if c4.button("None", key="pending_none"):
            for p in pending:
                st.session_state.pending_selected[p.name] = False
            st.rerun()

        for p in pending:
            swatch = color_map.get(p.name, INK)
            prob_dot = (
                f"<span style='font-family:var(--mono);font-size:0.7rem;"
                f"color:var(--muted);margin-left:6px;'>p={p.probability:g}</span>"
            )
            label = (
                f"<span style='display:inline-block;width:8px;height:8px;border-radius:50%;"
                f"background:{swatch};margin-right:6px;vertical-align:middle;opacity:0.55;"
                f"border:1px solid rgba(26,22,18,0.15);'></span>{p.name}{prob_dot}"
            )
            with st.container():
                st.session_state.pending_selected[p.name] = st.checkbox(
                    p.name,
                    value=st.session_state.pending_selected.get(p.name, False),
                    key=f"pending_{p.name}",
                    label_visibility="collapsed",
                    help=f"Probability of being funded: {p.probability:g}",
                )
                st.markdown(
                    f"<div style='margin:-32px 0 4px 30px;font-size:0.84rem;"
                    f"color:var(--ink);line-height:1.25;'>{label}</div>",
                    unsafe_allow_html=True,
                )

    # ---- Compute schedules --------------------------------------------
    selected_active = [
        p.name for p in active if st.session_state.active_selected.get(p.name)
    ]
    selected_pending = [
        p.name for p in pending if st.session_state.pending_selected.get(p.name)
    ]
    selected_names = tuple(sorted(set(selected_active) | set(selected_pending)))

    paced_result = _build_schedule(selected_names, start_date, num_weeks, "paced")
    frontload_result = _build_schedule(selected_names, start_date, num_weeks, "frontload")

    # ---- Masthead ------------------------------------------------------
    today = date.today().strftime("%Y-%m-%d").upper()
    horizon_end = start_date + timedelta(weeks=num_weeks)
    masthead = f"""
    <div class="masthead">
      <div>
        <span class="eyebrow">Vol. I &nbsp;·&nbsp; The Planner &nbsp;·&nbsp; {today}</span>
        <h1 class="masthead-title">Project <em>Planner</em></h1>
      </div>
      <div class="masthead-meta">
        <b>Horizon</b> {start_date} → {horizon_end}<br/>
        <b>Window</b> {num_weeks} weeks<br/>
        <b>Methods</b> paced &nbsp;·&nbsp; frontload
      </div>
    </div>
    """
    st.markdown(masthead, unsafe_allow_html=True)

    # ---- Hero stats ----------------------------------------------------
    selected_projects = [p for p in all_projects if p.name in selected_names]
    n_active = len(selected_active)
    n_pending = len(selected_pending)
    total_days = sum(p.remaining_days for p in selected_projects)

    at_risk = 0
    missed = 0
    if paced_result is not None:
        scheduler, sched = paced_result
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

    def _stat(label: str, value: str, sub: str = "", cls: str = "") -> str:
        sub_html = f"<div class='sub'>{sub}</div>" if sub else ""
        return (
            f"<div class='stat {cls}'>"
            f"<div class='label'>{label}</div>"
            f"<div class='value'>{value}</div>"
            f"{sub_html}"
            f"</div>"
        )

    stats = (
        "<div class='stats'>"
        + _stat("Active", f"{n_active:02d}", f"of {n_active_total:02d} on roster")
        + _stat("Pending", f"{n_pending:02d}", f"of {n_pending_total:02d} pipeline")
        + _stat("Total days", f"{total_days:g}", "selected workload")
        + _stat(
            "Tight", f"{at_risk:02d}",
            "<14d buffer" + (" — review" if at_risk else ""),
            "warn" if at_risk else "",
        )
        + _stat(
            "Missed", f"{missed:02d}",
            "deadline overrun" + (" — fix" if missed else ""),
            "danger" if missed else "",
        )
        + "</div>"
    )
    st.markdown(stats, unsafe_allow_html=True)

    # ---- Tabs ----------------------------------------------------------
    overview, paced, frontload, allocation, budget = st.tabs(
        ["Overview", "Paced", "Frontload", "Allocation", "Budget"]
    )

    with overview:
        st.markdown(_section_title("Calendar — paced", "01"), unsafe_allow_html=True)
        if paced_result is None:
            st.markdown("<div class='empty-note'>No projects selected.</div>",
                        unsafe_allow_html=True)
        else:
            fig = create_calendar_heatmap(paced_result[1], "", color_map)
            st.plotly_chart(_restyle_fig(fig) or _empty_fig("No data"),
                            width="stretch", key="overview_cal")

        st.markdown(_section_title("Availability over time", "02"), unsafe_allow_html=True)
        if paced_result is None or frontload_result is None:
            st.markdown("<div class='empty-note'>No projects selected.</div>",
                        unsafe_allow_html=True)
        else:
            fig = create_availability_plot(
                compute_weekly_availability(paced_result[1], num_weeks),
                compute_weekly_availability(frontload_result[1], num_weeks),
            )
            st.plotly_chart(_restyle_fig(fig), width="stretch", key="overview_avail")

    with paced:
        st.markdown(_section_title("Paced calendar", "01"), unsafe_allow_html=True)
        if paced_result is None:
            st.markdown("<div class='empty-note'>No projects selected.</div>",
                        unsafe_allow_html=True)
        else:
            fig = create_calendar_heatmap(paced_result[1], "", color_map)
            st.plotly_chart(_restyle_fig(fig) or _empty_fig("No data"),
                            width="stretch", key="paced_cal")
            st.markdown(_section_title("Unassigned days — by month", "02"),
                        unsafe_allow_html=True)
            st.dataframe(_unassigned_df(paced_result[1]), width="stretch")

    with frontload:
        st.markdown(_section_title("Frontload calendar", "01"), unsafe_allow_html=True)
        if frontload_result is None:
            st.markdown("<div class='empty-note'>No projects selected.</div>",
                        unsafe_allow_html=True)
        else:
            fig = create_calendar_heatmap(frontload_result[1], "", color_map)
            st.plotly_chart(_restyle_fig(fig) or _empty_fig("No data"),
                            width="stretch", key="frontload_cal")
            st.markdown(_section_title("Unassigned days — by month", "02"),
                        unsafe_allow_html=True)
            st.dataframe(_unassigned_df(frontload_result[1]), width="stretch")

    with allocation:
        st.markdown(_section_title("Weekly allocation — paced", "01"),
                    unsafe_allow_html=True)
        if paced_result is None:
            st.markdown("<div class='empty-note'>No projects selected.</div>",
                        unsafe_allow_html=True)
        else:
            fig = create_project_allocation_plot(paced_result[1], num_weeks, color_map)
            st.plotly_chart(_restyle_fig(fig) or _empty_fig("No data"),
                            width="stretch", key="alloc")

    with budget:
        st.markdown(_section_title("Paced — deadline budget", "01"),
                    unsafe_allow_html=True)
        if paced_result is None:
            st.markdown("<div class='empty-note'>No projects selected.</div>",
                        unsafe_allow_html=True)
        else:
            scheduler, sched = paced_result
            st.markdown(
                _budget_html(_budget_rows(sched, scheduler.projects), color_map),
                unsafe_allow_html=True,
            )

        st.markdown(_section_title("Frontload — deadline budget", "02"),
                    unsafe_allow_html=True)
        if frontload_result is None:
            st.markdown("<div class='empty-note'>No projects selected.</div>",
                        unsafe_allow_html=True)
        else:
            scheduler, sched = frontload_result
            st.markdown(
                _budget_html(_budget_rows(sched, scheduler.projects), color_map),
                unsafe_allow_html=True,
            )


main()
