from langchain_anthropic import ChatAnthropic

from job_matcher.nodes._common import build_scored_jobs
from job_matcher.prompts import (
    DREAMER_AGENT_SYSTEM_PROMPT,
    build_dreamer_agent_human_prompt,
)
from job_matcher.schemas import Preferences, ScoreAgentOutput
from job_matcher.state import OrchestratorState


def dreamer_agent(state: OrchestratorState) -> dict:
    llm = ChatAnthropic(model="claude-sonnet-5")
    prefs: Preferences = state["preferences"]

    messages = [
        ("system", DREAMER_AGENT_SYSTEM_PROMPT),
        (
            "user",
            build_dreamer_agent_human_prompt(
                prefs,
                state["resume_text"],
                state["candidate_profile"],
                state["context_signals"],
                state["job_listings"],
            ),
        ),
    ]
    decision: ScoreAgentOutput = llm.with_structured_output(ScoreAgentOutput).invoke(
        messages
    )

    return {
        "stretch_matches": build_scored_jobs(state["job_listings"], decision.scores)
    }
