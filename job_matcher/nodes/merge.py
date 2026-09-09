from job_matcher.state import OrchestratorState


def merge(state: OrchestratorState) -> dict:
    """Deterministic assembly — Score and Dreamer write disjoint keys, so this
    only sorts each list by fit_score. No LLM call by design."""
    realistic_matches = sorted(
        state["realistic_matches"],
        key=lambda scored_job: scored_job.fit_score,
        reverse=True,
    )
    stretch_matches = sorted(
        state["stretch_matches"],
        key=lambda scored_job: scored_job.fit_score,
        reverse=True,
    )
    return {
        "realistic_matches": realistic_matches,
        "stretch_matches": stretch_matches,
    }
