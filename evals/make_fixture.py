"""Freeze the Score/Dreamer inputs from a real run into a JSON fixture.

Reads the latest state of a checkpoint thread, so no new search is needed.
Usage: python -m evals.make_fixture [thread_id] [case_name]
"""
import json
import sys
from pathlib import Path

from job_matcher.graph import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def main() -> None:
    thread_id = sys.argv[1] if len(sys.argv) > 1 else "kushagra-main"
    case_name = sys.argv[2] if len(sys.argv) > 2 else "case_1"

    state = app.get_state({"configurable": {"thread_id": thread_id}}).values
    if not state.get("job_listings"):
        sys.exit(f"Thread {thread_id!r} has no job_listings — run a search first.")

    fixture = {
        "inputs": {
            "preferences": state["preferences"].model_dump(),
            "resume_text": state["resume_text"],
            "candidate_profile": state["candidate_profile"],
            "context_signals": state["context_signals"],
            "job_listings": [job.model_dump() for job in state["job_listings"]],
        },
        # Filled by hand: job_id -> "high" | "low" | "stretch"
        "labels": {},
    }

    FIXTURES_DIR.mkdir(exist_ok=True)
    out = FIXTURES_DIR / f"{case_name}.json"
    out.write_text(json.dumps(fixture, indent=2, ensure_ascii=False))
    print(f"Wrote {out} ({len(fixture['inputs']['job_listings'])} jobs)")


if __name__ == "__main__":
    main()
