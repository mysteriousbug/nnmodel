"""
Audit Scheduling Assistant — Streamlit UI
=========================================
Run: streamlit run app.py

A demo-ready UI that wraps audit_scheduler.py:
  - Upload all 5 input files (or use bundled test data)
  - Tune scoring weights and split heuristics live
  - Run the scheduler and inspect outputs:
      * Per-audit breakdown with TL, members, scores
      * Calendar grid (week × auditor) coloured by audit
      * Auditor workload chart
      * Warnings panel
  - Download the 3 generated xlsx outputs
"""

from __future__ import annotations

import io
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

# Import the scheduler module
sys.path.insert(0, str(Path(__file__).parent))
import audit_scheduler as sched  # noqa: E402

st.set_page_config(
    page_title="Audit Scheduling Assistant",
    page_icon="📋",
    layout="wide",
)

# ----------------------------------------------------------------------------
# Sidebar — config + inputs
# ----------------------------------------------------------------------------

st.sidebar.title("⚙️ Configuration")

with st.sidebar.expander("Scoring weights", expanded=False):
    w_skill = st.slider("Skill match", 0.0, 1.0, 0.35, 0.05)
    w_prior = st.slider("Prior experience", 0.0, 1.0, 0.30, 0.05)
    w_avail = st.slider("Availability", 0.0, 1.0, 0.20, 0.05)
    w_interest = st.slider("Interest (preference)", 0.0, 1.0, 0.15, 0.05)
    total_w = w_skill + w_prior + w_avail + w_interest
    if abs(total_w - 1.0) > 0.01:
        st.caption(f"⚠️ Weights sum to {total_w:.2f} (will be used as-is)")

with st.sidebar.expander("Team split heuristic", expanded=False):
    primary_share = st.slider("Primary team share", 0.30, 0.80, 0.50, 0.05)
    second_share = st.slider("Second team share", 0.15, 0.50, 0.30, 0.05)
    team_floor = st.slider("Minimum floor per team", 0.05, 0.25, 0.15, 0.05)
    analytics_bump = st.slider("DM bump if analytics", 0.0, 0.20, 0.10, 0.05)

with st.sidebar.expander("Skill inference", expanded=False):
    groq_key = st.text_input("Groq API Key (optional)", type="password",
                              help="Llama 3.3 70B infers required skills from audit titles. "
                                   "Leave blank to use keyword fallback.")
    if groq_key:
        import os
        os.environ["GROQ_API_KEY"] = groq_key

st.sidebar.divider()
st.sidebar.markdown("### 📁 Inputs")

data_source = st.sidebar.radio(
    "Data source",
    ["Use bundled test data", "Upload my own files"],
    index=0,
)

uploaded_files: dict[str, io.BytesIO] = {}
if data_source == "Upload my own files":
    for fname in ["leave_tracker", "skills", "planned_audits",
                  "planned_assignments", "interests"]:
        uf = st.sidebar.file_uploader(f"{fname}.xlsx", type=["xlsx"], key=fname)
        if uf:
            uploaded_files[fname] = uf

# ----------------------------------------------------------------------------
# Main pane
# ----------------------------------------------------------------------------

st.title("📋 Audit Scheduling Assistant")
st.caption("Standard Chartered GIA · ICS / T&A / DM · 2026 planning cycle")

# Apply config to scheduler module
sched.W_SKILL = w_skill
sched.W_PRIOR = w_prior
sched.W_AVAIL = w_avail
sched.W_INTEREST = w_interest
sched.BASE_SPLIT = {
    "primary": primary_share,
    "second": second_share,
    "third": max(0.05, 1.0 - primary_share - second_share),
}
sched.TEAM_FLOOR = team_floor
sched.ANALYTICS_DM_BUMP = analytics_bump

# Decide on input directory
def _stage_inputs() -> Path:
    """Materialise uploads (or bundled data) into a temp folder for the scheduler."""
    target = Path("./inputs")
    if data_source == "Upload my own files":
        target = Path("./streamlit_inputs")
        target.mkdir(exist_ok=True)
        for fname, buf in uploaded_files.items():
            (target / f"{fname}.xlsx").write_bytes(buf.getvalue())
    return target


# ----------------------------------------------------------------------------
# Run button
# ----------------------------------------------------------------------------

ready = (data_source == "Use bundled test data") or (len(uploaded_files) == 5)

col_run, col_status = st.columns([1, 4])
with col_run:
    run_clicked = st.button("▶️ Run scheduler", type="primary", disabled=not ready,
                             use_container_width=True)
with col_status:
    if not ready:
        st.info("Upload all 5 input files (or switch to bundled test data) to enable.")

if "results" not in st.session_state:
    st.session_state.results = None


def _run_scheduler():
    """Run the full pipeline, capture in-memory artefacts for the UI."""
    input_dir = _stage_inputs()
    sched.INPUT_DIR = input_dir
    out_dir = Path("./streamlit_outputs")
    out_dir.mkdir(exist_ok=True)
    sched.OUTPUT_DIR = out_dir

    with st.status("Running scheduler...", expanded=True) as status:
        st.write("Loading auditors and audits...")
        auditors = sched.load_auditors()
        audits = sched.load_audits()
        st.write(f"  → {len(auditors)} auditors, {len(audits)} audits")

        st.write("Computing durations and team-day splits...")
        for a in audits:
            sched.compute_duration(a)
            sched.compute_split(a)

        st.write("Inferring required skills...")
        sched.infer_skills_for_audits(audits)

        st.write("Solving assignments...")
        warnings = sched.solve(auditors, audits)
        st.write(f"  → {len(warnings)} warnings")

        st.write("Writing output workbooks...")
        sched.write_grid(auditors, audits, out_dir / "assignments_grid.xlsx")
        sched.write_summary(audits, auditors, out_dir / "assignments_summary.xlsx")
        sched.write_warnings(warnings, auditors, out_dir / "warnings.xlsx")

        status.update(label="✅ Done", state="complete", expanded=False)

    return {"auditors": auditors, "audits": audits, "warnings": warnings,
            "out_dir": out_dir}


if run_clicked:
    st.session_state.results = _run_scheduler()


# ----------------------------------------------------------------------------
# Results display
# ----------------------------------------------------------------------------

if st.session_state.results is None:
    st.markdown("---")
    st.markdown("""
    ### How it works
    
    1. **Loads** all 5 workbooks, unifies the auditor pool across ICS / T&A / DM teams.
    2. **Computes** each audit's window from its report date and total auditor-days.
    3. **Splits** auditor-days across teams using a 50/30/20 base + heuristic bumps
       (analytics → DM, infra keywords → T&A, security keywords → ICS).
    4. **Infers** required skills per audit via Groq + Llama 3.3 70B (cached).
    5. **Scores** every (auditor, audit) pair on skill / prior experience / availability / interest.
    6. **Assigns** greedily: earliest report date first, TL from primary team, preference-aware.
    
    Click **Run scheduler** to see results.
    """)
    st.stop()

results = st.session_state.results
auditors = results["auditors"]
audits = results["audits"]
warnings_list = results["warnings"]
out_dir: Path = results["out_dir"]

# ---------- Top metrics ----------

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Audits scheduled", len(audits))
m2.metric("Auditors", len(auditors))
assigned_count = sum(1 for a in audits if a.assigned_tl)
m3.metric("Audits with TL", f"{assigned_count}/{len(audits)}")
prefs_met = sum(1 for a in auditors.values()
                if a.preferences and a.preference_satisfied)
prefs_total = sum(1 for a in auditors.values() if a.preferences)
m4.metric("Preferences met", f"{prefs_met}/{prefs_total}")
m5.metric("Warnings", len(warnings_list),
          delta_color="inverse" if warnings_list else "off")

st.markdown("---")

# ---------- Tabs ----------

tab_summary, tab_grid, tab_workload, tab_warnings, tab_downloads = st.tabs([
    "📋 Per-Audit Summary",
    "📅 Calendar Grid",
    "👥 Auditor Workload",
    "⚠️ Warnings",
    "⬇️ Downloads",
])

# ---------- TAB: Per-Audit Summary ----------

with tab_summary:
    st.subheader("Per-audit assignments")

    audit_rows = []
    for a in sorted(audits, key=lambda x: x.report_date):
        scores = []
        if a.assigned_tl and a.assigned_tl in auditors:
            scores.append(sched.score(auditors[a.assigned_tl], a)[1]["skill"])
        for m_name, _, _ in a.assigned_members:
            if m_name in auditors:
                scores.append(sched.score(auditors[m_name], a)[1]["skill"])
        avg_skill = round(sum(scores) / len(scores), 2) if scores else 0.0

        audit_rows.append({
            "Audit": a.number,
            "Title": a.title,
            "Primary": a.primary_team,
            "Report Date": a.report_date.isoformat(),
            "Window": f"{a.start_date.strftime('%d %b')} → {a.end_date.strftime('%d %b')}",
            "Days": a.total_days,
            "Split (ICS/T&A/DM)": f"{a.team_days.get('ICS',0)}/{a.team_days.get('T&A',0)}/{a.team_days.get('DM',0)}",
            "TL": a.assigned_tl or "—",
            "Members": ", ".join(n for n, _, _ in a.assigned_members),
            "Skill Score": avg_skill,
        })
    df_summary = pd.DataFrame(audit_rows)
    st.dataframe(df_summary, use_container_width=True, hide_index=True,
                 column_config={
                     "Skill Score": st.column_config.ProgressColumn(
                         "Skill Score", min_value=0, max_value=1, format="%.2f"
                     ),
                 })

    # Detail expander per audit
    st.markdown("#### Drill into an audit")
    selected = st.selectbox(
        "Select an audit",
        options=[a.number for a in audits],
        format_func=lambda n: f"{n} — {next(a.title for a in audits if a.number == n)}",
    )
    audit = next(a for a in audits if a.number == selected)

    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown(f"**{audit.title}**")
        st.markdown(f"Primary team: `{audit.primary_team}` · "
                    f"Report: `{audit.report_date}` · "
                    f"Quarter: `{audit.quarter}`")
        st.markdown(f"Total auditor-days: `{audit.total_days}` · "
                    f"Fieldwork window: `{audit.duration_days}` working days")
        st.markdown(f"Window: `{audit.start_date}` → `{audit.end_date}`")
        st.markdown(f"Team-day split: "
                    f"ICS=`{audit.team_days.get('ICS',0)}`, "
                    f"T&A=`{audit.team_days.get('T&A',0)}`, "
                    f"DM=`{audit.team_days.get('DM',0)}`")
        st.markdown(f"Headcount: "
                    f"ICS=`{audit.team_headcount.get('ICS',0)}`, "
                    f"T&A=`{audit.team_headcount.get('T&A',0)}`, "
                    f"DM=`{audit.team_headcount.get('DM',0)}`")
        if audit.required_skills:
            st.markdown(f"Inferred required skills: "
                        + " ".join(f"`{s}`" for s in sorted(audit.required_skills)))
        if audit.required_certs:
            st.markdown(f"Relevant certs: "
                        + " ".join(f"`{c}`" for c in sorted(audit.required_certs)))

    with c2:
        st.markdown("**Assignments + score breakdown**")
        rows = []
        if audit.assigned_tl:
            aud = auditors[audit.assigned_tl]
            _, breakdown = sched.score(aud, audit)
            rows.append({
                "Role": "TL",
                "Name": aud.name,
                "Team": aud.home_team,
                "Skill": round(breakdown["skill"], 2),
                "Prior": round(breakdown["prior"], 2),
                "Avail": round(breakdown["avail"], 2),
                "Interest": int(breakdown["interest"]),
            })
        for m_name, m_team, _ in audit.assigned_members:
            if m_name in auditors:
                aud = auditors[m_name]
                _, breakdown = sched.score(aud, audit)
                rows.append({
                    "Role": aud.role,
                    "Name": aud.name,
                    "Team": aud.home_team,
                    "Skill": round(breakdown["skill"], 2),
                    "Prior": round(breakdown["prior"], 2),
                    "Avail": round(breakdown["avail"], 2),
                    "Interest": int(breakdown["interest"]),
                })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ---------- TAB: Calendar Grid ----------

with tab_grid:
    st.subheader("Weekly assignment grid")
    st.caption("Same format as `planned_assignments.xlsx`. One sheet per team.")

    team = st.radio("Team", sched.TEAMS, horizontal=True)

    from datetime import timedelta
    first_monday = date(sched.SCHEDULE_YEAR, 1, 5)
    weeks = [first_monday + timedelta(weeks=i) for i in range(52)]
    audit_by_num = {a.number: a for a in audits}

    team_auditors = sorted(
        [a for a in auditors.values() if a.home_team == team],
        key=lambda x: (x.role != "SAM", x.role, x.name),
    )

    grid_data = []
    for aud in team_auditors:
        row = {"Auditor": f"{aud.role}/{aud.name}"}
        for w in weeks:
            week_end = w + timedelta(days=4)
            cell = []
            for num in aud.assigned_audits:
                audit = audit_by_num[num]
                if audit.start_date <= week_end and audit.end_date >= w:
                    cell.append(audit.title.split("(")[0].strip()[:22])
            row[w.strftime("%d %b")] = "; ".join(cell)
        grid_data.append(row)

    df_grid = pd.DataFrame(grid_data)

    # Style: fill assigned cells
    def _highlight(val):
        if val and isinstance(val, str) and val.strip():
            return "background-color: #d4e5ff; color: #1a3a6e"
        return ""
    styled = df_grid.style.map(_highlight, subset=df_grid.columns[1:])

    st.dataframe(styled, use_container_width=True, height=400, hide_index=True)

# ---------- TAB: Auditor Workload ----------

with tab_workload:
    st.subheader("Auditor workload distribution")

    wl_rows = []
    for aud in sorted(auditors.values(), key=lambda x: (x.home_team, x.role, x.name)):
        wl_rows.append({
            "Auditor": aud.name,
            "Team": aud.home_team,
            "Role": aud.role,
            "Audits": len(aud.assigned_audits),
            "Days Booked": aud.days_booked,
            "Preference Met": (
                "✅" if aud.preference_satisfied
                else "—" if not aud.preferences
                else "❌"
            ),
        })
    df_wl = pd.DataFrame(wl_rows)

    c1, c2 = st.columns([1, 1])
    with c1:
        st.dataframe(df_wl, use_container_width=True, hide_index=True,
                     column_config={
                         "Days Booked": st.column_config.ProgressColumn(
                             "Days Booked", min_value=0, max_value=200, format="%d d",
                         ),
                     })
    with c2:
        # Days-booked chart
        chart_df = df_wl.set_index("Auditor")[["Days Booked"]]
        st.bar_chart(chart_df, height=400)

    st.markdown("#### Skill gaps")
    gap_rows = []
    for aud in auditors.values():
        relevant_audits = [a for a in audits
                           if aud.name == a.assigned_tl
                           or any(aud.name == n for n, _, _ in a.assigned_members)]
        for a in relevant_audits:
            missing = a.required_skills - aud.skills
            if missing and a.required_skills:
                gap_rows.append({
                    "Auditor": aud.name,
                    "Audit": a.number,
                    "Missing skills": ", ".join(sorted(missing)),
                })
    if gap_rows:
        st.caption("Skills required by an audit that the assigned auditor doesn't have. "
                   "Useful for identifying training needs.")
        st.dataframe(pd.DataFrame(gap_rows), use_container_width=True, hide_index=True)
    else:
        st.success("No skill gaps detected.")

# ---------- TAB: Warnings ----------

with tab_warnings:
    st.subheader("Scheduler warnings")
    if not warnings_list:
        st.success("✅ No warnings. All audits fully staffed within constraints.")
    else:
        for w in warnings_list:
            st.warning(w)

    st.markdown("#### Capacity overview")
    total_audit_days = sum(a.total_days for a in audits)
    working_days_year = sched.working_days_between(
        date(sched.SCHEDULE_YEAR, 1, 1),
        date(sched.SCHEDULE_YEAR, 12, 31),
    )
    capacity = len(auditors) * working_days_year
    utilisation = total_audit_days / capacity
    c1, c2, c3 = st.columns(3)
    c1.metric("Total auditor-days planned", f"{total_audit_days:,}")
    c2.metric("Annual capacity", f"{capacity:,}")
    c3.metric("Utilisation", f"{utilisation:.0%}")
    st.progress(min(1.0, utilisation))

# ---------- TAB: Downloads ----------

with tab_downloads:
    st.subheader("Download outputs")
    files = {
        "assignments_summary.xlsx": "📋 Per-audit summary",
        "assignments_grid.xlsx": "📅 Weekly grid",
        "warnings.xlsx": "⚠️ Warnings + workload",
    }
    for fname, label in files.items():
        path = out_dir / fname
        if path.exists():
            st.download_button(
                label=f"{label} ({fname})",
                data=path.read_bytes(),
                file_name=fname,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
