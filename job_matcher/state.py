from typing import Annotated, Literal, TypedDict

from job_matcher.schemas import JobListing, Preferences, ScoredJob
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage

class OrchestratorState(TypedDict):
    # --- input ---
    preferences: Preferences
    resume_text: str
    candidate_profile: str

    # --- written by Orchestrator ---
    job_listings: list[JobListing]
    expanded_keywords: list[str]  # kept visible for eval assertions
    context_signals: str          # Orchestrator's read of additional_context

    # --- written by Score / Dreamer (disjoint keys, plain overwrite, no reducer) ---
    realistic_matches: list[ScoredJob]
    stretch_matches: list[ScoredJob]

    run_id: str                                              # plain overwrite, set once at entry
    chat_history: Annotated[list[AnyMessage], add_messages]  # reducer — appends, understands RemoveMessage
    chat_summary: str

    intent: Literal["search", "chat"]   # caller (app.py) set karega
