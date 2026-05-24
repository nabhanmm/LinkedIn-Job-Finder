"""
LinkedIn Job Finder — Streamlit Web App
Wraps linkedin_jobs.py with a clean browser UI.
No Python installation needed for users.
"""

import io
import threading
from datetime import datetime
from queue import Queue, Empty

import pandas as pd
import streamlit as st

import linkedin_jobs as lj

# ─────────────────────────────────────────────────────────────────
# Page config (must be first Streamlit call)
# ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LinkedIn Job Finder",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────
# Custom CSS
# ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Fonts */
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=DM+Mono&display=swap');

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #0f172a;
    }
    [data-testid="stSidebar"] * {
        color: #e2e8f0 !important;
    }
    [data-testid="stSidebar"] .stTextInput input,
    [data-testid="stSidebar"] .stTextArea textarea {
        background: #1e293b !important;
        border: 1px solid #334155 !important;
        color: #f1f5f9 !important;
        border-radius: 6px;
    }
    [data-testid="stSidebar"] .stMultiSelect > div {
        background: #1e293b !important;
        border: 1px solid #334155 !important;
    }

    /* Metric cards */
    [data-testid="metric-container"] {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 12px 16px;
    }
    [data-testid="stMetricValue"] {
        font-size: 2rem !important;
        font-weight: 600 !important;
        color: #0f172a !important;
    }
    [data-testid="stMetricLabel"] {
        color: #64748b !important;
        font-size: 0.8rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* Primary button */
    .stButton > button[kind="primary"] {
        background: #2563eb !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        height: 48px !important;
        font-size: 1rem !important;
        transition: all 0.2s ease;
    }
    .stButton > button[kind="primary"]:hover {
        background: #1d4ed8 !important;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(37,99,235,0.35) !important;
    }

    /* Download buttons */
    .stDownloadButton > button {
        border-radius: 8px !important;
        font-weight: 500 !important;
    }

    /* Dataframe */
    [data-testid="stDataFrame"] {
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        overflow: hidden;
    }

    /* Log box */
    .log-box {
        background: #0f172a;
        color: #a3e635;
        font-family: 'DM Mono', monospace;
        font-size: 0.78rem;
        padding: 12px 16px;
        border-radius: 8px;
        max-height: 200px;
        overflow-y: auto;
        white-space: pre-wrap;
        line-height: 1.6;
    }

    /* Header */
    .app-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 4px;
    }
    .app-title {
        font-size: 2rem;
        font-weight: 700;
        color: #0f172a;
        margin: 0;
    }
    .app-subtitle {
        color: #64748b;
        font-size: 0.9rem;
        margin-bottom: 24px;
    }

    /* Match badge colours */
    .badge-strong { background:#dcfce7; color:#166534; padding:2px 10px; border-radius:99px; font-size:0.78rem; font-weight:600; }
    .badge-good   { background:#dbeafe; color:#1e40af; padding:2px 10px; border-radius:99px; font-size:0.78rem; font-weight:600; }
    .badge-neutral{ background:#f1f5f9; color:#475569; padding:2px 10px; border-radius:99px; font-size:0.78rem; font-weight:600; }

    /* Divider */
    hr { border-color: #e2e8f0 !important; margin: 1.2rem 0 !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────
# Session state initialisation
# ─────────────────────────────────────────────────────────────────
if "results" not in st.session_state:
    st.session_state.results = None
if "last_config" not in st.session_state:
    st.session_state.last_config = {}

# ─────────────────────────────────────────────────────────────────
# Sidebar — all filters
# ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔍 Job Search Filters")
    st.caption("Configure your search below, then hit **Search Jobs**.")
    st.markdown("---")

    job_title = st.text_input("🏷️ Job Title", value="Talent Acquisition Manager")

    LOCATION_OPTIONS = [
        "India", "Kochi", "Bangalore", "Mumbai", "Delhi", "Hyderabad",
        "Chennai", "Pune", "Bangkok", "Singapore", "Dubai", "Abu Dhabi",
        "United States", "United Kingdom", "Canada", "Australia", "Remote"
    ]
    locations = st.multiselect(
        "📍 Locations",
        options=LOCATION_OPTIONS,
        default=["India", "Kochi"],
    )

    work_modes = st.multiselect(
        "💼 Work Mode",
        options=["remote", "hybrid", "onsite"],
        default=["remote", "hybrid"],
    )

    exp_levels = st.multiselect(
        "📊 Experience Level",
        options=["internship", "entry", "associate", "mid-senior", "director", "executive"],
        default=["mid-senior"],
    )

    posted_days = st.select_slider(
        "📅 Posted Within",
        options=[1, 3, 7, 14, 30],
        value=7,
        format_func=lambda x: f"Last {x} day{'s' if x > 1 else ''}",
    )

    job_type = st.selectbox(
        "📋 Job Type",
        options=["full-time", "contract", "part-time", "any"],
        index=0,
    )

    col_a, col_b = st.columns(2)
    min_exp = col_a.number_input("Min Exp (yrs)", min_value=0, max_value=30, value=8, step=1)
    max_results = col_b.selectbox("Max Results", options=[10, 25, 50, 75, 100], index=2)

    st.markdown("---")

    with st.expander("🎯 Keyword Filters", expanded=False):
        preferred_text = st.text_area(
            "✅ Preferred Keywords (one per line)",
            value="analytics\ndata analytics\nIT services\nSaaS\nconsulting\nproduct\ntechnology\nAI\nmachine learning",
            height=130,
        )
        exclude_text = st.text_area(
            "🚫 Exclude Keywords (one per line)",
            value="BPO\nstaffing\nRPO\njunior\nassociate recruiter\nfresher\nentry level\nintern\nrelocation required",
            height=130,
        )

    with st.expander("🏢 Company Filter", expanded=False):
        companies_text = st.text_area(
            "Target Companies (one per line — leave empty for all)",
            value="",
            height=80,
            placeholder="e.g.\nFractal\nInfosys\nTata",
        )
        exclude_closed = st.toggle("Hide jobs no longer accepting", value=True)

    with st.expander("📧 Email Results (optional)", expanded=False):
        st.caption("Uses Gmail. Generate an App Password at myaccount.google.com → Security.")
        email_from     = st.text_input("From (Gmail)", "")
        email_password = st.text_input("App Password", "", type="password")
        email_to       = st.text_input("Send To", "")

    st.markdown("---")
    run = st.button("🚀 Search Jobs", type="primary", use_container_width=True)

    st.markdown("""
    <div style='color:#475569;font-size:0.72rem;margin-top:12px;line-height:1.6'>
    ℹ️ This tool scrapes LinkedIn's public guest API.<br>
    Results may vary depending on LinkedIn's rate limits.<br>
    Enrichment (Easy Apply, company info) adds ~2 sec per job.
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────
# Main header
# ─────────────────────────────────────────────────────────────────
st.markdown("""
<div class='app-header'>
  <span style='font-size:2.2rem'>🔍</span>
  <h1 class='app-title'>LinkedIn Job Finder</h1>
</div>
<p class='app-subtitle'>Search, filter, and download LinkedIn job listings — no Python required</p>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────
# Input validation
# ─────────────────────────────────────────────────────────────────
if run:
    errors = []
    if not job_title.strip():
        errors.append("Job Title cannot be empty.")
    if not locations:
        errors.append("Select at least one Location.")
    if not work_modes:
        errors.append("Select at least one Work Mode.")
    if not exp_levels:
        errors.append("Select at least one Experience Level.")
    if errors:
        for e in errors:
            st.error(e)
        st.stop()

# ─────────────────────────────────────────────────────────────────
# Run search
# ─────────────────────────────────────────────────────────────────
if run:
    cfg = {
        "job_title":            job_title.strip(),
        "location":             locations,
        "work_mode":            work_modes,
        "experience_level":     exp_levels,
        "job_type":             job_type,
        "posted_within_days":   posted_days,
        "min_years_experience": min_exp,
        "max_results":          max_results,
        "preferred_keywords":   [k.strip() for k in preferred_text.splitlines() if k.strip()],
        "exclude_keywords":     [k.strip() for k in exclude_text.splitlines() if k.strip()],
        "target_companies":     [c.strip() for c in companies_text.splitlines() if c.strip()],
        "exclude_closed_jobs":  exclude_closed,
        "skills":               ["ATS", "sourcing", "recruitment", "talent acquisition", "hiring"],
        "output_folder":        ".",
        "output_filename":      "linkedin_jobs_web.xlsx",
        "email_from":           email_from,
        "email_password":       email_password,
        "email_to":             email_to,
        "email_smtp":           "smtp.gmail.com",
        "email_port":           587,
        "schedule_time":        "10:00",
    }

    # ── Live log collector ───────────────────────────────────────
    log_lines   = []
    log_holder  = st.empty()

    def ui_log(msg):
        log_lines.append(msg)
        displayed = "\n".join(log_lines[-15:])
        log_holder.markdown(
            f"<div class='log-box'>{displayed}</div>",
            unsafe_allow_html=True
        )

    # Patch the module-level log function so all internal calls route here
    lj.log = ui_log

    # ── Search ───────────────────────────────────────────────────
    with st.status("Searching LinkedIn…", expanded=True) as status:

        combo_count = len(locations) * len(work_modes) * len(exp_levels)
        st.write(
            f"**{job_title}** · {', '.join(locations)} · "
            f"{', '.join(work_modes)} · {combo_count} search combination(s)"
        )

        prog = st.progress(0, text="Fetching job cards…")

        # Step 1 — fetch cards
        st.write("**Step 1 / 2** — Fetching listings from LinkedIn…")
        jobs = lj.fetch_all_combinations(cfg)
        prog.progress(40, text=f"{len(jobs)} listings found — now enriching…")

        if not jobs:
            status.update(label="No results found", state="error")
            st.warning(
                "LinkedIn returned no jobs for these filters. "
                "Try a broader location, shorter time window, or different experience levels."
            )
            st.stop()

        # Step 2 — enrich
        st.write(f"**Step 2 / 2** — Enriching {len(jobs)} jobs (Easy Apply · company info · closed check)…")
        st.caption("This takes ~2 seconds per job. Grab a coffee ☕")
        jobs = lj.enrich_jobs(jobs, cfg)
        prog.progress(100, text="Done!")

        status.update(label=f"✅ {len(jobs)} matching jobs found!", state="complete")

    log_holder.empty()      # clear the terminal-style log after completion
    st.session_state.results    = jobs
    st.session_state.last_config = cfg

    # Email (if configured)
    if email_from and email_to and jobs:
        df_tmp = pd.DataFrame(jobs)
        buf    = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df_tmp.to_excel(w, index=False, sheet_name="LinkedIn Jobs")
            lj.apply_styles_and_dropdown(w.sheets["LinkedIn Jobs"], len(df_tmp))
        buf.seek(0)
        tmp_path = f"/tmp/linkedin_jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        with open(tmp_path, "wb") as f:
            f.write(buf.read())
        lj.send_email(tmp_path, len(jobs), cfg)

# ─────────────────────────────────────────────────────────────────
# Results panel
# ─────────────────────────────────────────────────────────────────
if st.session_state.results:
    jobs = st.session_state.results
    df   = pd.DataFrame(jobs)

    # Ensure all columns exist
    for col in lj.COL_ORDER:
        if col not in df.columns:
            df[col] = ""
    df = df[lj.COL_ORDER]

    # ── Metrics row ──────────────────────────────────────────────
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Jobs",    len(df))
    m2.metric("Strong Match",  len(df[df["Match"] == "Strong"]))
    m3.metric("Good Match",    len(df[df["Match"] == "Good"]))
    m4.metric("Easy Apply",    len(df[df["Easy Apply"] == "Yes"]))
    m5.metric("Still Open",    len(df[df["Still Accepting?"] == "Yes"]))

    st.markdown("---")

    # ── Table filters ────────────────────────────────────────────
    f1, f2, f3, f4 = st.columns([2, 2, 2, 2])

    all_matches   = sorted(df["Match"].dropna().unique().tolist())
    all_easy      = sorted(df["Easy Apply"].dropna().unique().tolist())
    all_open      = sorted(df["Still Accepting?"].dropna().unique().tolist())
    all_locations = sorted(df["Location"].dropna().unique().tolist())

    sel_match    = f1.multiselect("Match",          all_matches,   default=all_matches,  key="f_match")
    sel_easy     = f2.multiselect("Easy Apply",     all_easy,      default=all_easy,     key="f_easy")
    sel_open     = f3.multiselect("Still Accepting",all_open,      default=all_open,     key="f_open")
    sel_location = f4.multiselect("Location",       all_locations, default=all_locations,key="f_loc")

    mask = (
        df["Match"].isin(sel_match) &
        df["Easy Apply"].isin(sel_easy) &
        df["Still Accepting?"].isin(sel_open) &
        df["Location"].isin(sel_location)
    )
    filtered_df = df[mask].copy()

    st.caption(f"Showing **{len(filtered_df)}** of **{len(df)}** jobs")

    # ── Dataframe ────────────────────────────────────────────────
    st.dataframe(
        filtered_df,
        use_container_width=True,
        hide_index=True,
        height=480,
        column_config={
            "Applied?": st.column_config.SelectboxColumn(
                "Applied?",
                options=["", "Relevant", "Applied", "Irrelevant - Criteria mismatch"],
                width="medium",
            ),
            "Job Title": st.column_config.TextColumn("Job Title", width="large"),
            "Company":   st.column_config.TextColumn("Company",   width="medium"),
            "LinkedIn URL": st.column_config.LinkColumn(
                "LinkedIn URL", display_text="🔗 View", width="small"
            ),
            "Recruiter Profile": st.column_config.LinkColumn(
                "Recruiter", display_text="👤 Profile", width="small"
            ),
            "Match":            st.column_config.TextColumn("Match",    width="small"),
            "Easy Apply":       st.column_config.TextColumn("Easy Apply", width="small"),
            "Still Accepting?": st.column_config.TextColumn("Open?",    width="small"),
            "Posted Date":      st.column_config.TextColumn("Posted",   width="small"),
            "Exp. Required":    st.column_config.TextColumn("Exp. Req", width="small"),
        },
    )

    st.markdown("---")

    # ── Download buttons ─────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M")

    dl1, dl2, _ = st.columns([1, 1, 2])

    # CSV
    csv_bytes = filtered_df.to_csv(index=False).encode("utf-8")
    dl1.download_button(
        label="⬇️ Download CSV",
        data=csv_bytes,
        file_name=f"linkedin_jobs_{ts}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    # Excel (styled, with dropdowns — matches original script output)
    excel_buf = io.BytesIO()
    with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
        filtered_df.to_excel(writer, index=False, sheet_name="LinkedIn Jobs")
        lj.apply_styles_and_dropdown(writer.sheets["LinkedIn Jobs"], len(filtered_df))
    excel_buf.seek(0)

    dl2.download_button(
        label="⬇️ Download Excel",
        data=excel_buf,
        file_name=f"linkedin_jobs_{ts}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    st.caption(
        "💡 The Excel file includes colour-coded match quality, "
        "hyperlinked job titles, and an **Applied?** dropdown in column A — "
        "identical to the original script output."
    )

elif not run:
    # Empty state
    st.markdown("""
    <div style='text-align:center; padding: 60px 0; color:#94a3b8'>
        <div style='font-size:4rem; margin-bottom:16px'>📋</div>
        <div style='font-size:1.2rem; font-weight:600; color:#475569; margin-bottom:8px'>
            Configure your filters and click Search Jobs
        </div>
        <div style='font-size:0.9rem'>
            Results will appear here with match scoring, Easy Apply detection,<br>
            company info, and one-click Excel/CSV download.
        </div>
    </div>
    """, unsafe_allow_html=True)
