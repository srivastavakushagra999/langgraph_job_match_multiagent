from typing import TypedDict

from job_matcher.schemas import JobListing, Preferences, ScoredJob


class OrchestratorState(TypedDict):
    # --- input ---
    preferences: Preferences
    resume_text: str

    # --- written by Orchestrator ---
    job_listings: list[JobListing]
    expanded_keywords: list[str]  # kept visible for eval assertions
    context_signals: str          # Orchestrator's read of additional_context

    # --- written by Score / Dreamer (disjoint keys, plain overwrite, no reducer) ---
    realistic_matches: list[ScoredJob]
    stretch_matches: list[ScoredJob]
