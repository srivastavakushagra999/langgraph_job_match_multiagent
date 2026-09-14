from langchain_core.tools import tool

from job_matcher.memory.memory import _connect

MAX_ROWS = 25


@tool
def get_job_by_id(job_id: str) -> str:
    """Look up the full job posting text for one job, using the id shown as
    [job_id: ...]. Use this when the candidate asks what a posting actually
    says or requires - its description is not in your context. Returns the
    most recently stored version of that job."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT created_at, bucket, position, company, location, url,
                   salary_min, salary_max, description,
                   fit_score, reasoning, gap_suggestion
            FROM run_jobs
            WHERE job_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()

    if row is None:
        return f"No stored job with job_id {job_id!r}."

    return (
        f"[job_id: {job_id}] {row['position']} - {row['company']}\n"
        f"Location: {row['location']}\n"
        f"Salary: {row['salary_min'] or 'unknown'} - {row['salary_max'] or 'unknown'}\n"
        f"URL: {row['url']}\n"
        f"Bucket: {row['bucket']} | Fit score: {row['fit_score']}/100\n"
        f"Stored from a search on {row['created_at'][:10]}\n"
        f"Reasoning: {row['reasoning']}\n"
        f"Gap suggestion: {row['gap_suggestion']}\n"
        f"--- FULL POSTING ---\n{row['description']}"
    )


@tool
def query_past_runs(
    role: str | None = None,
    position: str | None = None,
    company: str | None = None,
    min_fit_score: int | None = None,
    limit: int = 10,
    summary_only: bool = False,
) -> str:
    """Search jobs stored by earlier search runs. Use this for questions about
    previous searches - what came up before, whether a company or job has
    appeared in earlier runs, or how scores have changed over time. All
    filters are optional; omit them all to see the most recent results.
    All three text filters match partial text: `position` is the job's own
    title (e.g. 'Senior AI Engineer'), `company` is the employer, and `role`
    is what the candidate searched for, not the job's title. To find a job the
    user named, use `position` and/or `company`.
    Leave summary_only=False (the default) for almost everything, including
    any question naming or listing jobs, even when the user mentions a past
    run - that mode returns the jobs themselves with titles, companies and
    ids. Set summary_only=True ONLY when the user wants statistics about
    searches as a whole, such as whether scores improved between searches: it
    returns per-search averages with NO job titles or ids at all, so it cannot
    name a single job. Returns a compact list without posting
    text - call get_job_by_id for the full posting of any job."""
    clauses, params = [], []
    if role:
        clauses.append("role LIKE ?")
        params.append(f"%{role}%")
    if position:
        clauses.append("position LIKE ?")
        params.append(f"%{position}%")
    if company:
        clauses.append("company LIKE ?")
        params.append(f"%{company}%")
    if min_fit_score is not None:
        clauses.append("fit_score >= ?")
        params.append(min_fit_score)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(limit, MAX_ROWS)))

    if summary_only:
        with _connect() as conn:
            runs = conn.execute(
                f"""
                SELECT created_at, role, jobs_scanned,
                       COUNT(*) AS matches,
                       ROUND(AVG(fit_score)) AS avg_score,
                       MAX(fit_score) AS best_score
                FROM run_jobs
                {where}
                GROUP BY run_id
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

        if not runs:
            return "No stored runs match those filters."

        lines = [
            f"{r['created_at'][:10]} | searched {r['role']!r} | "
            f"{r['jobs_scanned']} jobs scanned | {r['matches']} matches | "
            f"avg fit {int(r['avg_score'])}/100 | best {r['best_score']}/100"
            for r in runs
        ]
        return f"{len(runs)} past run(s), newest first:\n" + "\n".join(lines)

    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT created_at, role, keywords, jobs_scanned,
                   job_id, bucket, position, company, location,
                   salary_min, salary_max, fit_score
            FROM run_jobs
            {where}
            ORDER BY created_at DESC, fit_score DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    if not rows:
        return "No stored jobs match those filters."

    lines = [
        f"{r['created_at'][:10]} | searched {r['role']!r} ({r['jobs_scanned']} jobs scanned) | "
        f"{r['bucket']} {r['fit_score']}/100 | {r['position']} - {r['company']} "
        f"({r['location']}) [job_id: {r['job_id']}]"
        for r in rows
    ]
    return f"{len(rows)} stored job(s), newest first:\n" + "\n".join(lines)
