import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from job_matcher.state import OrchestratorState

DB_PATH = Path(__file__).parent.parent / "data" / "memory.sqlite"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
                CREATE TABLE IF NOT EXISTS run_jobs (
                    run_id          TEXT NOT NULL,
                    thread_id       TEXT NOT NULL,
                    created_at      TEXT NOT NULL,
                    role            TEXT,
                    base_location   TEXT,
                    keywords        TEXT,
                    context_signals TEXT,
                    jobs_scanned    INTEGER,
                    job_id     TEXT NOT NULL,
                    bucket     TEXT NOT NULL,
                    position TEXT, company TEXT, location TEXT, url TEXT,
                    salary_min REAL, salary_max REAL,
                    description TEXT,
                    fit_score INTEGER, reasoning TEXT, gap_suggestion TEXT,
                    PRIMARY KEY (run_id, job_id, bucket)
                );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_run_jobs_job_id ON run_jobs(job_id)")


def _row(run_id, thread_id, created_at, prefs, keywords_json, context_signals,
         jobs_scanned, bucket, scored):
    job = scored.job
    return (
        run_id, thread_id, created_at,
        prefs.role, prefs.base_location, keywords_json, context_signals, jobs_scanned,
        job.id, bucket,
        job.position, job.company, job.location, job.url,
        job.salary_min, job.salary_max, job.description,
        scored.fit_score, scored.reasoning, scored.gap_suggestion,
    )


def save_run(state: OrchestratorState, thread_id: str) -> None:
    init_db()
    run_id = state["run_id"]
    prefs = state["preferences"]
    created_at = datetime.now(timezone.utc).isoformat()
    keywords_json = json.dumps(state["expanded_keywords"])
    jobs_scanned = len(state["job_listings"])

    rows = [
        _row(run_id, thread_id, created_at, prefs, keywords_json,
             state["context_signals"], jobs_scanned, "realistic", scored)
        for scored in state["realistic_matches"]
    ] + [
        _row(run_id, thread_id, created_at, prefs, keywords_json,
             state["context_signals"], jobs_scanned, "stretch", scored)
        for scored in state["stretch_matches"]
    ]

    with _connect() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO run_jobs (
                run_id, thread_id, created_at,
                role, base_location, keywords, context_signals, jobs_scanned,
                job_id, bucket,
                position, company, location, url,
                salary_min, salary_max, description,
                fit_score, reasoning, gap_suggestion
            ) VALUES (?,?,?, ?,?,?,?,?, ?,?, ?,?,?,?, ?,?,?, ?,?,?)
            """,
            rows,
        )
