from job_matcher.schemas import JobListing, JobScore, ScoredJob


def build_scored_jobs(
    job_listings: list[JobListing],
    scores: list[JobScore],
) -> list[ScoredJob]:
    """Attach each LLM-produced score back to its full JobListing.

    Scores referencing an unknown job_id (hallucinated or stale) are dropped.
    Shared by score_agent and dreamer_agent — identical post-processing.
    """
    jobs_by_id = {job.id: job for job in job_listings}

    scored_jobs: list[ScoredJob] = []
    for score in scores:
        job = jobs_by_id.get(score.job_id)
        if job is None:
            continue
        scored_jobs.append(
            ScoredJob(
                job=job,
                fit_score=score.fit_score,
                reasoning=score.reasoning,
                gap_suggestion=score.gap_suggestion,
            )
        )
    return scored_jobs
