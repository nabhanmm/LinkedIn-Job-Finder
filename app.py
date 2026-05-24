"""
LinkedIn Job Finder — v2
Features: User auth (Supabase), persistent repository, deduplication, status tracking
"""

import io
from datetime import datetime

import pandas as pd
import streamlit as st
from supabase import create_client

import linkedin_jobs as lj

# ─────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LinkedIn Job Finder",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=DM+Mono&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

[data-testid="stSidebar"] { background: #0f172a; }
[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stTextArea textarea {
    background: #1e293b !important; border: 1px solid #334155 !important; color: #f1f5f9 !important;
}
[data-testid="stSidebar"] .stMultiSelect > div { background: #1e293b !important; border: 1px solid #334155 !important; }

[data-testid="metric-container"] {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px 16px;
}
[data-testid="stMetricValue"] { font-size: 2rem !important; font-weight: 600 !important; color: #0f172a !important; }
[data-testid="stMetricLabel"] { color: #64748b !important; font-size: 0.8rem !important; text-transform: uppercase; letter-spacing: 0.05em; }

.stButton > button[kind="primary"] {
    background: #2563eb !important; color: white !important; border: none !important;
    border-radius: 8px !important; font-weight: 600 !important; height: 48px !important; font-size: 1rem !important;
}
.stButton > button[kind="primary"]:hover { background: #1d4ed8 !important; }
.stDownloadButton > button { border-radius: 8px !important; font-weight: 500 !important; }
[data-testid="stDataFrame"] { border: 1px solid #e2e8f0; border-radius: 10px; overflow: hidden; }
.log-box {
    background: #0f172a; color: #a3e635; font-family: 'DM Mono', monospace;
    font-size: 0.78rem; padding: 12px 16px; border-radius: 8px;
    max-height: 200px; overflow-y: auto; white-space: pre-wrap; line-height: 1.6;
}
hr { border-color: #e2e8f0 !important; margin: 1.2rem 0 !important; }
.auth-card {
    background: #fff; border: 1px solid #e2e8f0; border-radius: 16px;
    padding: 2rem 2rem; box-shadow: 0 4px 24px rgba(0,0,0,0.06);
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────
# Supabase client (cached so it's created once per session)
# ─────────────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_ANON_KEY"],
    )

supabase = get_supabase()


# ─────────────────────────────────────────────────────────────────
# Session state initialisation
# ─────────────────────────────────────────────────────────────────
DEFAULTS = {
    "user":          None,
    "access_token":  None,
    "refresh_token": None,
    "results":       None,
    "new_count":     0,
    "dup_count":     0,
    "auth_mode":     "signin",   # "signin" | "signup"
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Restore Supabase session from stored tokens (survives Streamlit reruns)
if st.session_state.access_token and st.session_state.user is None:
    try:
        res = supabase.auth.set_session(
            st.session_state.access_token,
            st.session_state.refresh_token,
        )
        st.session_state.user = res.user
    except Exception:
        st.session_state.access_token  = None
        st.session_state.refresh_token = None


# ─────────────────────────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────────────────────────
def do_signup(email: str, password: str, username: str):
    try:
        res = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"username": username}},
        })
        return res.user, None
    except Exception as e:
        return None, str(e)

def do_signin(email: str, password: str):
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        return res, None
    except Exception as e:
        return None, str(e)

def do_signout():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    for k in ["user", "access_token", "refresh_token", "results"]:
        st.session_state[k] = None
    st.rerun()


# ─────────────────────────────────────────────────────────────────
# Repository DB helpers
# ─────────────────────────────────────────────────────────────────
def get_repository(user_id: str) -> list:
    res = (
        supabase.table("job_repository")
        .select("*")
        .eq("user_id", user_id)
        .order("date_added", desc=True)
        .execute()
    )
    return res.data or []


def get_existing_urls(user_id: str) -> set:
    res = (
        supabase.table("job_repository")
        .select("linkedin_url")
        .eq("user_id", user_id)
        .execute()
    )
    return {r["linkedin_url"] for r in (res.data or []) if r.get("linkedin_url")}


def append_new_jobs(jobs: list, user) -> tuple:
    """Saves only genuinely new jobs. Returns (new_count, dup_count)."""
    existing   = get_existing_urls(user.id)
    new_jobs   = [j for j in jobs if j.get("LinkedIn URL", "") not in existing]
    dup_count  = len(jobs) - len(new_jobs)

    if not new_jobs:
        return 0, dup_count

    username = (user.user_metadata or {}).get("username", "")
    rows = [{
        "user_id":           user.id,
        "user_email":        user.email,
        "username":          username,
        "job_title":         j.get("Job Title", ""),
        "company":           j.get("Company", ""),
        "company_size":      j.get("Company Size", ""),
        "company_type":      j.get("Company Type", ""),
        "level":             j.get("Level", ""),
        "location":          j.get("Location", ""),
        "work_mode":         j.get("Work Mode", ""),
        "linkedin_url":      j.get("LinkedIn URL", ""),
        "match":             j.get("Match", ""),
        "easy_apply":        j.get("Easy Apply", ""),
        "still_accepting":   j.get("Still Accepting?", ""),
        "posted_date":       j.get("Posted Date", ""),
        "date_searched":     j.get("Date Searched", ""),
        "exp_required":      j.get("Exp. Required", ""),
        "recruiter_profile": j.get("Recruiter Profile", ""),
        "status":            "New",
        "date_added":        datetime.now().isoformat(),
    } for j in new_jobs]

    supabase.table("job_repository").insert(rows).execute()
    return len(new_jobs), dup_count


def update_job_status(row_id: str, status: str):
    supabase.table("job_repository").update({"status": status}).eq("id", row_id).execute()


# ─────────────────────────────────────────────────────────────────
# AUTH PAGE
# ─────────────────────────────────────────────────────────────────
def show_auth_page():
    st.markdown("""
    <div style='text-align:center; padding:40px 0 24px;'>
        <div style='font-size:3.5rem;'>🔍</div>
        <h1 style='font-size:2rem; font-weight:700; margin:8px 0 6px; color:#0f172a;'>LinkedIn Job Finder</h1>
        <p style='color:#64748b; font-size:0.95rem;'>Search smarter. Track everything. Apply with confidence.</p>
    </div>
    """, unsafe_allow_html=True)

    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        mode = st.radio(
            "Account",
            ["Sign In", "Create Account"],
            horizontal=True,
            label_visibility="collapsed",
        )
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        if mode == "Create Account":
            username = st.text_input("Your Name", placeholder="e.g. Arjun Nair")
            email    = st.text_input("Email address", placeholder="arjun@gmail.com")
            pw       = st.text_input("Password", type="password", placeholder="Min 6 characters")
            pw2      = st.text_input("Confirm Password", type="password")

            if st.button("Create Account", type="primary", use_container_width=True):
                errors = []
                if not username.strip(): errors.append("Please enter your name.")
                if not email.strip():    errors.append("Please enter your email.")
                if not pw:               errors.append("Please enter a password.")
                if pw != pw2:            errors.append("Passwords do not match.")
                if pw and len(pw) < 6:   errors.append("Password must be at least 6 characters.")

                if errors:
                    for e in errors:
                        st.error(e)
                else:
                    user, err = do_signup(email.strip(), pw, username.strip())
                    if err:
                        st.error(f"Sign up failed: {err}")
                    else:
                        st.success(
                            "✅ Account created! Check your email for a verification link, "
                            "then come back and Sign In."
                        )

        else:
            email = st.text_input("Email address")
            pw    = st.text_input("Password", type="password")

            if st.button("Sign In", type="primary", use_container_width=True):
                if not email or not pw:
                    st.error("Please enter your email and password.")
                else:
                    res, err = do_signin(email.strip(), pw)
                    if err:
                        st.error("Sign in failed. Check your credentials or verify your email first.")
                    else:
                        st.session_state.user          = res.user
                        st.session_state.access_token  = res.session.access_token
                        st.session_state.refresh_token = res.session.refresh_token
                        st.rerun()

        st.markdown("""
        <div style='text-align:center; margin-top:20px; font-size:12px; color:#94a3b8; line-height:1.8;'>
            🔒 Your job searches are private and only visible to you.<br>
            The admin can see registered email addresses for access management.
        </div>
        """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────
# MAIN APP (authenticated)
# ─────────────────────────────────────────────────────────────────
def show_main_app():
    user     = st.session_state.user
    username = (user.user_metadata or {}).get("username", user.email.split("@")[0])

    # ── Sidebar ──────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("## 🔍 Job Search Filters")

        # User badge
        st.markdown(f"""
        <div style='background:#1e293b; border-radius:8px; padding:10px 14px; margin-bottom:10px;'>
            <div style='font-size:13px; font-weight:500;'>👤 {username}</div>
            <div style='font-size:11px; color:#94a3b8;'>{user.email}</div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("Sign Out", use_container_width=True):
            do_signout()

        st.markdown("---")

        job_title = st.text_input("🏷️ Job Title", value="Talent Acquisition Manager")

        LOCATION_OPTIONS = [
            "India", "Kochi", "Bangalore", "Mumbai", "Delhi", "Hyderabad",
            "Chennai", "Pune", "Bangkok", "Singapore", "Dubai", "Abu Dhabi",
            "United States", "United Kingdom", "Canada", "Australia", "Remote",
        ]
        locations  = st.multiselect("📍 Locations",  LOCATION_OPTIONS, default=["India", "Kochi"])
        work_modes = st.multiselect("💼 Work Mode",  ["remote", "hybrid", "onsite"], default=["remote", "hybrid"])
        exp_levels = st.multiselect("📊 Experience Level",
            ["internship", "entry", "associate", "mid-senior", "director", "executive"],
            default=["mid-senior"])

        posted_days = st.select_slider(
            "📅 Posted Within",
            options=[1, 3, 7, 14, 30], value=7,
            format_func=lambda x: f"Last {x} day{'s' if x > 1 else ''}",
        )
        job_type = st.selectbox("📋 Job Type", ["full-time", "contract", "part-time", "any"], index=0)

        col_a, col_b = st.columns(2)
        min_exp     = col_a.number_input("Min Exp (yrs)", min_value=0, max_value=30, value=8, step=1)
        max_results = col_b.selectbox("Max Results", [10, 25, 50, 75, 100], index=2)

        st.markdown("---")

        with st.expander("🎯 Keyword Filters", expanded=False):
            preferred_text = st.text_area(
                "✅ Preferred Keywords (one per line)",
                value="analytics\ndata analytics\nIT services\nSaaS\nconsulting\nproduct\ntechnology\nAI\nmachine learning",
                height=120,
            )
            exclude_text = st.text_area(
                "🚫 Exclude Keywords (one per line)",
                value="BPO\nstaffing\nRPO\njunior\nassociate recruiter\nfresher\nentry level\nintern\nrelocation required",
                height=100,
            )

        with st.expander("🏢 Company Filter", expanded=False):
            companies_text = st.text_area("Target Companies (leave empty for all)", value="", height=70)
            exclude_closed = st.toggle("Hide closed jobs", value=True)

        with st.expander("📧 Email Results (optional)", expanded=False):
            email_from     = st.text_input("From (Gmail)", "")
            email_password = st.text_input("App Password", "", type="password")
            email_to       = st.text_input("Send To", "")

        st.markdown("---")
        run = st.button("🚀 Search Jobs", type="primary", use_container_width=True)

        st.markdown("""
        <div style='color:#475569; font-size:0.72rem; margin-top:12px; line-height:1.7;'>
        ℹ️ New results are automatically checked against your repository and duplicates are skipped.
        </div>
        """, unsafe_allow_html=True)

    # ── Tabs ─────────────────────────────────────────────────────
    tab_search, tab_repo = st.tabs(["🔍 Search Results", "📁 My Job Repository"])

    # ═══════════════════════════════════════════════════════════
    # TAB 1 — SEARCH
    # ═══════════════════════════════════════════════════════════
    with tab_search:
        st.markdown(f"""
        <div style='display:flex; align-items:center; gap:12px; margin-bottom:4px;'>
          <span style='font-size:2rem;'>🔍</span>
          <h1 style='font-size:1.8rem; font-weight:700; color:#0f172a; margin:0;'>LinkedIn Job Finder</h1>
        </div>
        <p style='color:#64748b; margin-bottom:20px;'>Welcome, <strong>{username}</strong>! Set your filters in the sidebar and click Search Jobs.</p>
        """, unsafe_allow_html=True)

        if run:
            # Validate inputs
            errors = []
            if not job_title.strip(): errors.append("Job Title cannot be empty.")
            if not locations:         errors.append("Select at least one Location.")
            if not work_modes:        errors.append("Select at least one Work Mode.")
            if not exp_levels:        errors.append("Select at least one Experience Level.")
            for e in errors:
                st.error(e)
            if errors:
                st.stop()

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

            # Live log
            log_lines  = []
            log_holder = st.empty()

            def ui_log(msg):
                log_lines.append(msg)
                rendered = "\n".join(log_lines[-15:])
                log_holder.markdown(
                    f"<div class='log-box'>{rendered}</div>",
                    unsafe_allow_html=True,
                )
            lj.log = ui_log

            with st.status("Searching LinkedIn…", expanded=True) as status:
                st.write(f"**{job_title}** · {', '.join(locations)} · {', '.join(work_modes)}")
                prog = st.progress(0, text="Fetching listings…")

                st.write("**Step 1/3** — Fetching from LinkedIn…")
                jobs = lj.fetch_all_combinations(cfg)
                prog.progress(35, text=f"{len(jobs)} listings found — enriching…")

                if not jobs:
                    status.update(label="No results found", state="error")
                    st.warning("No jobs found. Try broader filters (more locations, longer time window).")
                    st.stop()

                st.write(f"**Step 2/3** — Enriching {len(jobs)} jobs (Easy Apply, company info)…")
                jobs = lj.enrich_jobs(jobs, cfg)
                prog.progress(75, text="Checking for duplicates and saving…")

                st.write("**Step 3/3** — Deduplicating and saving to your repository…")
                new_count, dup_count = append_new_jobs(jobs, user)
                st.session_state.results   = jobs
                st.session_state.new_count = new_count
                st.session_state.dup_count = dup_count

                prog.progress(100, text="Done!")
                label = f"✅ Done! {new_count} new job(s) saved to your repository"
                if dup_count:
                    label += f" · {dup_count} duplicate(s) skipped"
                status.update(label=label, state="complete")

            log_holder.empty()

            # Email if configured
            if email_from and email_to and jobs:
                buf = io.BytesIO()
                tmp_df = pd.DataFrame(jobs)
                for col in lj.COL_ORDER:
                    if col not in tmp_df.columns:
                        tmp_df[col] = ""
                with pd.ExcelWriter(buf, engine="openpyxl") as w:
                    tmp_df[lj.COL_ORDER].to_excel(w, index=False, sheet_name="LinkedIn Jobs")
                    lj.apply_styles_and_dropdown(w.sheets["LinkedIn Jobs"], len(tmp_df))
                buf.seek(0)
                tmp_path = f"/tmp/jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                with open(tmp_path, "wb") as f:
                    f.write(buf.read())
                lj.send_email(tmp_path, new_count, cfg)

        # ── Results panel ─────────────────────────────────────
        if st.session_state.results:
            jobs = st.session_state.results
            df   = pd.DataFrame(jobs)
            for col in lj.COL_ORDER:
                if col not in df.columns:
                    df[col] = ""
            df = df[lj.COL_ORDER]

            new_c = st.session_state.new_count
            dup_c = st.session_state.dup_count

            # Dedup banner
            if dup_c and dup_c > 0:
                st.info(
                    f"**{new_c} new job(s)** added to your repository · "
                    f"**{dup_c} duplicate(s)** skipped — already in your repository from a previous search."
                )
            elif new_c is not None:
                st.success(f"**{new_c} new job(s)** added to your repository. No duplicates found.")

            # Metrics
            m1, m2, m3, m4, m5, m6 = st.columns(6)
            m1.metric("Total Found",  len(df))
            m2.metric("New to Repo",  new_c or 0)
            m3.metric("Duplicates",   dup_c or 0)
            m4.metric("Strong Match", len(df[df["Match"] == "Strong"]))
            m5.metric("Easy Apply",   len(df[df["Easy Apply"] == "Yes"]))
            m6.metric("Still Open",   len(df[df["Still Accepting?"] == "Yes"]))

            st.markdown("---")

            # Table-level filters
            f1, f2, f3, f4 = st.columns(4)
            all_matches = sorted(df["Match"].dropna().unique().tolist())
            all_easy    = sorted(df["Easy Apply"].dropna().unique().tolist())
            all_open    = sorted(df["Still Accepting?"].dropna().unique().tolist())
            all_locs    = sorted(df["Location"].dropna().unique().tolist())

            sel_match = f1.multiselect("Match",           all_matches, default=all_matches, key="sr_m")
            sel_easy  = f2.multiselect("Easy Apply",      all_easy,    default=all_easy,    key="sr_e")
            sel_open  = f3.multiselect("Still Accepting", all_open,    default=all_open,    key="sr_o")
            sel_loc   = f4.multiselect("Location",        all_locs,    default=all_locs,    key="sr_l")

            mask = (
                df["Match"].isin(sel_match) &
                df["Easy Apply"].isin(sel_easy) &
                df["Still Accepting?"].isin(sel_open) &
                df["Location"].isin(sel_loc)
            )
            fdf = df[mask].copy()
            st.caption(f"Showing **{len(fdf)}** of **{len(df)}** results  ·  Go to **My Job Repository** tab to update statuses")

            st.dataframe(
                fdf,
                use_container_width=True,
                hide_index=True,
                height=460,
                column_config={
                    "Applied?":          st.column_config.SelectboxColumn("Applied?",
                        options=["", "Relevant", "Applied", "Irrelevant - Criteria mismatch"], width="medium"),
                    "Job Title":         st.column_config.TextColumn("Job Title", width="large"),
                    "Company":           st.column_config.TextColumn("Company", width="medium"),
                    "LinkedIn URL":      st.column_config.LinkColumn("LinkedIn", display_text="🔗 View", width="small"),
                    "Recruiter Profile": st.column_config.LinkColumn("Recruiter", display_text="👤", width="small"),
                    "Match":             st.column_config.TextColumn("Match", width="small"),
                    "Easy Apply":        st.column_config.TextColumn("Easy Apply", width="small"),
                    "Still Accepting?":  st.column_config.TextColumn("Open?", width="small"),
                    "Posted Date":       st.column_config.TextColumn("Posted", width="small"),
                    "Exp. Required":     st.column_config.TextColumn("Exp.", width="small"),
                },
            )

            st.markdown("---")
            dl1, dl2, _ = st.columns([1, 1, 2])
            ts = datetime.now().strftime("%Y%m%d_%H%M")

            dl1.download_button(
                "⬇️ Download CSV",
                fdf.to_csv(index=False).encode("utf-8"),
                f"jobs_{ts}.csv", "text/csv",
                use_container_width=True,
            )
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as w:
                fdf.to_excel(w, index=False, sheet_name="LinkedIn Jobs")
                lj.apply_styles_and_dropdown(w.sheets["LinkedIn Jobs"], len(fdf))
            buf.seek(0)
            dl2.download_button(
                "⬇️ Download Excel",
                buf,
                f"jobs_{ts}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            st.caption("💡 Excel includes colour-coded match quality and the Applied? dropdown — same as the original script.")

        elif not run:
            st.markdown("""
            <div style='text-align:center; padding:60px 0; color:#94a3b8;'>
              <div style='font-size:4rem; margin-bottom:16px;'>📋</div>
              <div style='font-size:1.2rem; font-weight:600; color:#475569; margin-bottom:8px;'>
                Configure filters in the sidebar and click Search Jobs
              </div>
              <div style='font-size:0.9rem;'>
                Results appear here. New jobs are automatically saved to your repository<br>
                and duplicates from previous searches are skipped.
              </div>
            </div>
            """, unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════
    # TAB 2 — REPOSITORY
    # ═══════════════════════════════════════════════════════════
    with tab_repo:
        st.markdown("""
        <div style='display:flex; align-items:center; gap:12px; margin-bottom:4px;'>
          <span style='font-size:2rem;'>📁</span>
          <h1 style='font-size:1.8rem; font-weight:700; color:#0f172a; margin:0;'>My Job Repository</h1>
        </div>
        <p style='color:#64748b; margin-bottom:20px;'>
          Every job found across all your searches — deduplicated. Update your status in the
          <strong>Status ✏️</strong> column — click any cell to change it.
        </p>
        """, unsafe_allow_html=True)

        with st.spinner("Loading your repository…"):
            repo_data = get_repository(user.id)

        if not repo_data:
            st.markdown("""
            <div style='text-align:center; padding:60px 0; color:#94a3b8;'>
              <div style='font-size:4rem; margin-bottom:16px;'>📭</div>
              <div style='font-size:1.2rem; font-weight:600; color:#475569; margin-bottom:8px;'>
                Your repository is empty
              </div>
              <div style='font-size:0.9rem;'>
                Run a search and your jobs will automatically appear here.
              </div>
            </div>
            """, unsafe_allow_html=True)
            return

        repo_df = pd.DataFrame(repo_data)

        # ── Metrics ──────────────────────────────────────────
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Jobs",  len(repo_df))
        m2.metric("New",         len(repo_df[repo_df["status"] == "New"]))
        m3.metric("Relevant",    len(repo_df[repo_df["status"] == "Relevant"]))
        m4.metric("Applied",     len(repo_df[repo_df["status"] == "Applied"]))
        m5.metric("Irrelevant",  len(repo_df[repo_df["status"] == "Irrelevant"]))

        st.markdown("---")

        # ── Filters ──────────────────────────────────────────
        rf1, rf2, rf3, rf4 = st.columns(4)
        all_statuses  = ["New", "Relevant", "Applied", "Irrelevant"]
        all_r_matches = sorted(repo_df["match"].dropna().unique().tolist())
        all_r_locs    = sorted(repo_df["location"].dropna().unique().tolist())
        all_r_comps   = sorted(repo_df["company"].dropna().unique().tolist())

        sel_st   = rf1.multiselect("Status",   all_statuses,  default=all_statuses,  key="rp_st")
        sel_rm   = rf2.multiselect("Match",    all_r_matches, default=all_r_matches, key="rp_m")
        sel_rl   = rf3.multiselect("Location", all_r_locs,    default=all_r_locs,    key="rp_l")
        sel_rc   = rf4.multiselect("Company",  all_r_comps,   default=all_r_comps,   key="rp_c")

        rmask = (
            repo_df["status"].isin(sel_st) &
            repo_df["match"].isin(sel_rm) &
            repo_df["location"].isin(sel_rl) &
            repo_df["company"].isin(sel_rc)
        )
        filtered_repo = repo_df[rmask].copy().reset_index(drop=True)
        st.caption(f"Showing **{len(filtered_repo)}** of **{len(repo_df)}** jobs  ·  Click any **Status ✏️** cell to update")

        # ── Columns to display ───────────────────────────────
        DISPLAY_COLS = [
            "status", "job_title", "company", "location", "match",
            "easy_apply", "still_accepting", "posted_date", "exp_required",
            "work_mode", "level", "linkedin_url", "recruiter_profile", "date_added",
        ]
        for col in DISPLAY_COLS:
            if col not in filtered_repo.columns:
                filtered_repo[col] = ""

        display_df = filtered_repo[DISPLAY_COLS].copy()

        # ── Editable data editor — only Status is editable ───
        edited_df = st.data_editor(
            display_df,
            use_container_width=True,
            hide_index=True,
            height=500,
            key="repo_editor",
            column_config={
                "status":          st.column_config.SelectboxColumn(
                    "Status ✏️",
                    options=["New", "Relevant", "Applied", "Irrelevant"],
                    width="medium",
                    required=True,
                ),
                "job_title":       st.column_config.TextColumn("Job Title",   width="large"),
                "company":         st.column_config.TextColumn("Company",     width="medium"),
                "location":        st.column_config.TextColumn("Location",    width="small"),
                "match":           st.column_config.TextColumn("Match",       width="small"),
                "easy_apply":      st.column_config.TextColumn("Easy Apply",  width="small"),
                "still_accepting": st.column_config.TextColumn("Open?",       width="small"),
                "posted_date":     st.column_config.TextColumn("Posted",      width="small"),
                "exp_required":    st.column_config.TextColumn("Exp. Req.",   width="small"),
                "work_mode":       st.column_config.TextColumn("Mode",        width="small"),
                "level":           st.column_config.TextColumn("Level",       width="small"),
                "linkedin_url":    st.column_config.LinkColumn("LinkedIn",    display_text="🔗 View", width="small"),
                "recruiter_profile": st.column_config.LinkColumn("Recruiter", display_text="👤",      width="small"),
                "date_added":      st.column_config.TextColumn("Added On",    width="medium"),
            },
            disabled=[c for c in DISPLAY_COLS if c != "status"],
        )

        # Detect status changes and persist to Supabase
        orig_status   = display_df["status"].reset_index(drop=True)
        edited_status = edited_df["status"].reset_index(drop=True)
        changed_mask  = orig_status != edited_status

        if changed_mask.any():
            changed_idxs = changed_mask[changed_mask].index.tolist()
            for idx in changed_idxs:
                row_id     = filtered_repo.iloc[idx]["id"]
                new_status = edited_df.iloc[idx]["status"]
                update_job_status(row_id, new_status)
            st.success(f"✅ {len(changed_idxs)} status update(s) saved.")
            st.rerun()

        st.markdown("---")

        # ── Download repository ───────────────────────────────
        dl1, dl2, _ = st.columns([1, 1, 2])
        ts = datetime.now().strftime("%Y%m%d_%H%M")

        RENAME = {
            "status": "Status", "job_title": "Job Title", "company": "Company",
            "location": "Location", "match": "Match", "easy_apply": "Easy Apply",
            "still_accepting": "Still Accepting?", "posted_date": "Posted Date",
            "exp_required": "Exp. Required", "work_mode": "Work Mode", "level": "Level",
            "linkedin_url": "LinkedIn URL", "recruiter_profile": "Recruiter Profile",
            "date_added": "Date Added",
        }
        download_df = filtered_repo[DISPLAY_COLS].copy().rename(columns=RENAME)

        dl1.download_button(
            "⬇️ Download CSV",
            download_df.to_csv(index=False).encode("utf-8"),
            f"repository_{ts}.csv", "text/csv",
            use_container_width=True,
        )

        buf2 = io.BytesIO()
        with pd.ExcelWriter(buf2, engine="openpyxl") as w:
            download_df.to_excel(w, index=False, sheet_name="Job Repository")
            lj.apply_styles_and_dropdown(w.sheets["Job Repository"], len(download_df))
        buf2.seek(0)
        dl2.download_button(
            "⬇️ Download Excel",
            buf2,
            f"repository_{ts}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        st.caption(
            "💡 The Status column is editable directly in the table above. "
            "All other columns are read-only. Changes save instantly."
        )


# ─────────────────────────────────────────────────────────────────
# MAIN ROUTER
# ─────────────────────────────────────────────────────────────────
if st.session_state.user is None:
    show_auth_page()
else:
    show_main_app()
