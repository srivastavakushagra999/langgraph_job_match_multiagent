from langgraph.graph import StateGraph, START, END
from job_matcher.state import OrchestratorState
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from job_matcher.schemas import Preferences, OrchestratorDecision, ScoreAgentOutput, ScoredJob
from job_matcher.tools import search_jobs, _map_country_code, filter_top_jobs
from job_matcher.prompts import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    build_orchestrator_human_prompt,
    SCORE_AGENT_SYSTEM_PROMPT,
    build_score_agent_human_prompt,
    DREAMER_AGENT_SYSTEM_PROMPT,
    build_dreamer_agent_human_prompt,
)

# --- node stubs — replace each body with real logic one at a time ---

def orchestrator(state: OrchestratorState) -> dict:
    load_dotenv()
    llm = ChatAnthropic(model="claude-haiku-4-5-20251001")
    prefs: Preferences = state["preferences"]
    resume_text = state["resume_text"]

    messages = [
        ("system", ORCHESTRATOR_SYSTEM_PROMPT),
        ("user", build_orchestrator_human_prompt(prefs, resume_text)),
    ]
    decision: OrchestratorDecision = llm.with_structured_output(OrchestratorDecision).invoke(messages)

    country_code = _map_country_code(prefs.base_location)
    jobs = search_jobs(decision.expanded_keywords, country_code)
    jobs = filter_top_jobs(jobs, decision.expanded_keywords, limit=30)

    return {
        "job_listings": jobs,
        "expanded_keywords": decision.expanded_keywords,
        "context_signals": decision.context_signals,
    }


def score_agent(state: OrchestratorState) -> dict:
    load_dotenv()
    llm = ChatAnthropic(model="claude-sonnet-5")
    prefs: Preferences = state["preferences"]

    messages = [
        ("system", SCORE_AGENT_SYSTEM_PROMPT),
        ("user", build_score_agent_human_prompt(
            prefs, state["resume_text"], state["context_signals"], state["job_listings"],
        )),
    ]
    decision: ScoreAgentOutput = llm.with_structured_output(ScoreAgentOutput).invoke(messages)

    jobs_by_id = {job.id: job for job in state["job_listings"]}
    realistic_matches = []
    for score in decision.scores:
        job = jobs_by_id.get(score.job_id)
        if job is None:
            continue
        realistic_matches.append(ScoredJob(
            job=job,
            fit_score=score.fit_score,
            reasoning=score.reasoning,
            gap_suggestion=score.gap_suggestion,
        ))

    return {"realistic_matches": realistic_matches}


def dreamer_agent(state: OrchestratorState) -> dict:
    load_dotenv()
    llm = ChatAnthropic(model="claude-sonnet-5")
    prefs: Preferences = state["preferences"]

    messages = [
        ("system", DREAMER_AGENT_SYSTEM_PROMPT),
        ("user", build_dreamer_agent_human_prompt(
            prefs,
            state["resume_text"],
            state["candidate_profile"],
            state["context_signals"],
            state["job_listings"],
        )),
    ]
    decision: ScoreAgentOutput = llm.with_structured_output(ScoreAgentOutput).invoke(messages)

    jobs_by_id = {job.id: job for job in state["job_listings"]}
    stretch_matches = []
    for score in decision.scores:
        job = jobs_by_id.get(score.job_id)
        if job is None:
            continue
        stretch_matches.append(ScoredJob(
            job=job,
            fit_score=score.fit_score,
            reasoning=score.reasoning,
            gap_suggestion=score.gap_suggestion,
        ))

    return {"stretch_matches": stretch_matches}


def merge(state: OrchestratorState) -> dict:
    realistic_matches = sorted(
        state["realistic_matches"], key=lambda scored_job: scored_job.fit_score, reverse=True
    )
    stretch_matches = sorted(
        state["stretch_matches"], key=lambda scored_job: scored_job.fit_score, reverse=True
    )
    return {
        "realistic_matches": realistic_matches,
        "stretch_matches": stretch_matches,
    }


# --- wiring ---

graph = StateGraph(OrchestratorState)
graph.add_node("orchestrator", orchestrator)
graph.add_node("score_agent", score_agent)
graph.add_node("dreamer_agent", dreamer_agent)
graph.add_node("merge", merge)

graph.add_edge(START, "orchestrator")
graph.add_edge("orchestrator", "score_agent")
graph.add_edge("orchestrator", "dreamer_agent")
graph.add_edge("score_agent", "merge")
graph.add_edge("dreamer_agent", "merge")
graph.add_edge("merge", END)

app = graph.compile()
