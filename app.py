import os
import tempfile
from pathlib import Path

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from job_matcher.graph import app as job_matcher_app
from job_matcher.resume import parse_resume
from job_matcher.schemas import Preferences, ScoredJob
from job_matcher.tools import COUNTRY_CODE_MAP

DEFAULT_RESUME_PATH = "job_matcher/data/resume.pdf"
CANDIDATE_PROFILE_PATH = "job_matcher/data/candidate_profile_kushagra.txt"

# One checkpoint thread for now — single-user app. Everything the graph needs
# (preferences, resume, matches, chat history) is restored from this thread, so
# a chat turn only sends the new question.
THREAD_ID = "kushagra-main"
CONFIG = {"configurable": {"thread_id": THREAD_ID}}

SEARCH_MARKER = "🔍 New search run"

NODE_LABELS = {
    "orchestrator": "Searching jobs & expanding keywords",
    "score_agent": "Scoring realistic matches",
    "dreamer_agent": "Scoring stretch matches",
    "merge": "Finalizing results",
}

st.set_page_config(
    page_title="CareerLens",
    page_icon=":material/work_history:",
    layout="wide",
)


# --- helpers ---

def message_text(msg) -> str:
    """Anthropic responses can come back as a list of content blocks."""
    if isinstance(msg.content, list):
        return "".join(b.get("text", "") for b in msg.content if isinstance(b, dict))
    return msg.content


def score_badge(score: int) -> str:
    color = "green" if score >= 80 else "orange" if score >= 60 else "gray"
    return f":{color}-badge[{score}/100 fit]"


def format_salary(job) -> str | None:
    if not job.salary_min and not job.salary_max:
        return None
    low = f"{int(job.salary_min):,}" if job.salary_min else "?"
    high = f"{int(job.salary_max):,}" if job.salary_max else "?"
    return f"{low} – {high}"


def render_job_card(scored_job: ScoredJob, gap_label: str, gap_icon: str) -> None:
    job = scored_job.job
    with st.container(border=True):
        st.markdown(f"#### {job.position}")
        st.markdown(
            f"**{job.company}** &nbsp;·&nbsp; :material/location_on: {job.location} "
            f"&nbsp;·&nbsp; {score_badge(scored_job.fit_score)}"
        )

        salary = format_salary(job)
        if salary:
            st.caption(f":material/payments: {salary}")

        st.write(scored_job.reasoning)

        with st.expander(gap_label, icon=gap_icon):
            st.write(scored_job.gap_suggestion)

        with st.container(horizontal=True):
            st.link_button("View listing", job.url, icon=":material/open_in_new:")
            st.caption(f"job_id: {job.id}")


# --- sidebar: search form ---

with st.sidebar:
    st.markdown("### :material/search: New search")

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
            "Open to onsite if the job is in my base location",
            value=False,
        )
        additional_context = st.text_area(
            "Anything else about what you're looking for (optional)",
            placeholder="e.g. career-change motivation, industries to avoid, salary context",
        )
        resume_file = st.file_uploader("Resume (PDF)", type=["pdf"])

        submitted = st.form_submit_button(
            "Find matches", icon=":material/travel_explore:", width="stretch"
        )

    st.caption(f"Session: `{THREAD_ID}`")


# --- header ---

st.title("CareerLens")
st.caption("AI-powered job matching against your resume and preferences.")


# --- search run ---

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

    search_input = {
        "preferences": preferences,
        "resume_text": resume_text,
        "candidate_profile": candidate_profile,
        # intent goes on every invoke: it is persisted in the checkpoint, so a
        # stale "chat" would misroute this form submit.
        "intent": "search",
    }

    with st.status("Running CareerLens...", expanded=True) as status:
        try:
            for chunk in job_matcher_app.stream(search_input, CONFIG, stream_mode="updates"):
                for node_name in chunk:
                    status.write(f"✅ {NODE_LABELS.get(node_name, node_name)}")
        except Exception as exc:
            status.update(label="Failed", state="error")
            st.error(f"Something went wrong while matching jobs: {exc}")
            st.stop()
        status.update(label="Done", state="complete")


# --- results + chat, both read from the checkpoint ---

result = job_matcher_app.get_state(CONFIG).values
realistic_matches = result.get("realistic_matches", [])
stretch_matches = result.get("stretch_matches", [])

if not result:
    st.info(
        "Fill in the search form in the sidebar to get started.",
        icon=":material/arrow_back:",
    )
    st.stop()

preferences = result.get("preferences")
all_matches = realistic_matches + stretch_matches
top_score = max((m.fit_score for m in all_matches), default=0)

metric_cols = st.columns(4, border=True)
metric_cols[0].metric("Searched for", preferences.role if preferences else "—")
metric_cols[1].metric("Jobs scanned", len(result.get("job_listings", [])))
metric_cols[2].metric("Realistic / stretch", f"{len(realistic_matches)} / {len(stretch_matches)}")
metric_cols[3].metric("Top fit score", f"{top_score}/100")

if keywords := result.get("expanded_keywords"):
    st.caption("Keywords searched: " + " ".join(f":blue-badge[{k}]" for k in keywords))

results_col, chat_col = st.columns([3, 2], gap="medium")

with results_col:
    realistic_tab, stretch_tab = st.tabs(
        [f"Realistic matches ({len(realistic_matches)})", f"Stretch goals ({len(stretch_matches)})"]
    )

    with realistic_tab:
        if not realistic_matches:
            st.info("No realistic matches found.", icon=":material/search_off:")
        for scored_job in realistic_matches:
            render_job_card(scored_job, "How to close the gap", ":material/trending_up:")

    with stretch_tab:
        if not stretch_matches:
            st.info("No stretch matches found.", icon=":material/search_off:")
        for scored_job in stretch_matches:
            render_job_card(scored_job, "Roadmap to get there", ":material/rocket_launch:")

with chat_col:
    st.markdown("### :material/forum: Ask about your matches")

    chat_history = result.get("chat_history", [])
    with st.container(border=True, height=560):
        if len(chat_history) <= 1:
            st.caption(
                "Ask anything about these results — why a job scored the way it did, "
                "how your resume lines up, what to learn next."
            )

        for msg in chat_history:
            text = message_text(msg)
            if isinstance(msg, AIMessage) and text.startswith(SEARCH_MARKER):
                st.caption(text)
                continue
            # Tool traffic lives in chat_history too. The raw tool output is
            # for the model, not the user; the tool-call message is shown as a
            # one-line note so the lookup isn't invisible.
            if isinstance(msg, ToolMessage):
                continue
            if isinstance(msg, AIMessage) and msg.tool_calls:
                names = ", ".join(tc["name"] for tc in msg.tool_calls)
                st.caption(f":material/search: Checking past searches ({names})")
                continue
            role_name = "user" if isinstance(msg, HumanMessage) else "assistant"
            with st.chat_message(role_name):
                st.write(text)

    if question := st.chat_input("Ask about your matches", submit_mode="disable"):
        with st.spinner("Thinking..."):
            job_matcher_app.invoke(
                {"chat_history": [HumanMessage(question)], "intent": "chat"},
                CONFIG,
            )
        st.rerun()
