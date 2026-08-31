import os
import tempfile
from pathlib import Path

import streamlit as st

from job_matcher.graph import app as job_matcher_app
from job_matcher.resume import parse_resume
from job_matcher.schemas import Preferences, ScoredJob
from job_matcher.tools import COUNTRY_CODE_MAP

DEFAULT_RESUME_PATH = "job_matcher/data/resume.pdf"
CANDIDATE_PROFILE_PATH = "job_matcher/data/candidate_profile_kushagra.txt"

st.set_page_config(page_title="CareerLens", layout="wide")
st.title("CareerLens")
st.caption("AI-powered job matching against your resume and preferences.")

with st.form("preferences_form"):
    role = st.text_input("Target role", placeholder="e.g. AI Engineer")
    remote = st.checkbox("Remote", value=True)

    col1, col2 = st.columns(2)
    with col1:
        salary_min = st.number_input("Minimum salary", min_value=0, step=1000, value=100000)
    with col2:
        currency = st.selectbox("Currency", ["EUR", "USD", "GBP"])

    base_location = st.selectbox("Base location", sorted(COUNTRY_CODE_MAP.keys()))
    open_to_onsite_at_base = st.checkbox(
        "Open to onsite if the job is physically located in my base location",
        value=False,
    )
    additional_context = st.text_area(
        "Anything else about yourself or what you're looking for (optional)",
        placeholder="e.g. career-change motivation, industries to avoid, salary context",
    )
    resume_file = st.file_uploader("Resume (PDF)", type=["pdf"])

    submitted = st.form_submit_button("Find matches")

if submitted:
    if not role.strip():
        st.error("Please enter a target role.")
        st.stop()

    tmp_resume_path = None
    try:
        if resume_file is not None:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(resume_file.read())
                tmp_resume_path = tmp.name
            resume_path = tmp_resume_path
            st.caption("Using uploaded resume.")
        elif Path(DEFAULT_RESUME_PATH).exists():
            resume_path = DEFAULT_RESUME_PATH
            st.caption(f"No resume uploaded — using default on file ({DEFAULT_RESUME_PATH}).")
        else:
            st.error(
                f"No resume uploaded and no default found at {DEFAULT_RESUME_PATH}. "
                "Please upload a resume."
            )
            st.stop()

        resume_text = parse_resume(resume_path)
    finally:
        if tmp_resume_path is not None:
            os.unlink(tmp_resume_path)

    candidate_profile = Path(CANDIDATE_PROFILE_PATH).read_text()

    preferences = Preferences(
        role=role,
        remote=remote,
        salary_min=salary_min,
        currency=currency,
        base_location=base_location,
        open_to_onsite_at_base=open_to_onsite_at_base,
        additional_context=additional_context or None,
    )

    NODE_LABELS = {
        "orchestrator": "Searching jobs & expanding keywords",
        "score_agent": "Scoring realistic matches",
        "dreamer_agent": "Scoring stretch matches",
        "merge": "Finalizing results",
    }

    state = {
        "preferences": preferences,
        "resume_text": resume_text,
        "candidate_profile": candidate_profile,
    }

    with st.status("Running CareerLens...", expanded=True) as status:
        try:
            for chunk in job_matcher_app.stream(state, stream_mode="updates"):
                for node_name, node_output in chunk.items():
                    status.write(f"✅ {NODE_LABELS.get(node_name, node_name)}")
                    state.update(node_output)
        except Exception as exc:
            status.update(label="Failed", state="error")
            st.error(f"Something went wrong while matching jobs: {exc}")
            st.stop()
        status.update(label="Done", state="complete")

    st.session_state["result"] = state

if "result" in st.session_state:
    result = st.session_state["result"]

    def render_job_card(scored_job: ScoredJob, gap_label: str) -> None:
        job = scored_job.job
        with st.container(border=True):
            st.subheader(f"{job.position} — {job.company}")
            st.write(f"**Fit score:** {scored_job.fit_score}/100")
            st.write(f"**Location:** {job.location}")
            if job.salary_min or job.salary_max:
                st.write(f"**Salary:** {job.salary_min or '?'} – {job.salary_max or '?'}")
            st.write(f"**Reasoning:** {scored_job.reasoning}")
            st.write(f"**{gap_label}:** {scored_job.gap_suggestion}")
            st.markdown(f"[View listing]({job.url})")

    realistic_tab, stretch_tab = st.tabs(["Realistic Matches", "Stretch Goals"])

    with realistic_tab:
        realistic_matches = result.get("realistic_matches", [])
        if not realistic_matches:
            st.info("No realistic matches found.")
        for scored_job in realistic_matches:
            render_job_card(scored_job, "How to close the gap")

    with stretch_tab:
        stretch_matches = result.get("stretch_matches", [])
        if not stretch_matches:
            st.info("No stretch matches found.")
        for scored_job in stretch_matches:
            render_job_card(scored_job, "Roadmap to get there")
