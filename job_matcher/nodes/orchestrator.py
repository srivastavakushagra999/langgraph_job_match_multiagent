from langchain_anthropic import ChatAnthropic

from job_matcher.prompts import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    build_orchestrator_human_prompt,
)
from job_matcher.schemas import OrchestratorDecision, Preferences
from job_matcher.state import OrchestratorState
from job_matcher.tools import _map_country_code, filter_top_jobs, search_jobs
import uuid
from langchain_core.messages import AIMessage


def orchestrator(state: OrchestratorState) -> dict:
    llm = ChatAnthropic(model="claude-haiku-4-5-20251001")
    prefs: Preferences = state["preferences"]
    resume_text = state["resume_text"]

    messages = [
        ("system", ORCHESTRATOR_SYSTEM_PROMPT),
        ("user", build_orchestrator_human_prompt(prefs, resume_text)),
    ]
    decision: OrchestratorDecision = llm.with_structured_output(
        OrchestratorDecision
    ).invoke(messages)

    country_code = _map_country_code(prefs.base_location)
    jobs = search_jobs(decision.expanded_keywords, country_code)
    jobs = filter_top_jobs(jobs, decision.expanded_keywords, limit=30)

    return {
        "job_listings": jobs,
        "expanded_keywords": decision.expanded_keywords,
        "context_signals": decision.context_signals,
        "run_id": str(uuid.uuid4()),
        "chat_history": [
            AIMessage(content=f"🔍 New search run — keywords: {', '.join(decision.expanded_keywords)}")
        ],
    }
