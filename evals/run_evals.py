"""Run Score + Dreamer on the frozen dataset and grade the outputs.

Usage: python -m evals.run_evals [experiment_prefix]
"""
import sys
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from langsmith import evaluate

from job_matcher.nodes import dreamer_agent, score_agent
from job_matcher.schemas import JobListing, Preferences, ScoredJob
from evals.upload_dataset import DATASET_NAME

HIGH_MIN = 70     # "high" label passes if Score gives >= this
LOW_MAX = 40      # "low" label passes if Score gives < this
STRONG_MIN = 75   # Score fit at/above this is a safe match, not a stretch


def _dump(matches: list[ScoredJob]) -> list[dict]:
    return [
        {
            "job_id": m.job.id,
            "fit_score": m.fit_score,
            "reasoning": m.reasoning,
            "gap_suggestion": m.gap_suggestion,
        }
        for m in matches
    ]


def target(inputs: dict) -> dict:
    state = {
        **inputs,
        "preferences": Preferences(**inputs["preferences"]),
        "job_listings": [JobListing(**j) for j in inputs["job_listings"]],
    }
    # Same fan-out as the graph: both agents see the same input, in parallel.
    with ThreadPoolExecutor(max_workers=2) as pool:
        score = pool.submit(score_agent, state)
        dream = pool.submit(dreamer_agent, state)
        realistic = score.result()["realistic_matches"]
        stretch = dream.result()["stretch_matches"]
    return {"realistic": _dump(realistic), "stretch": _dump(stretch)}


# --- evaluators -------------------------------------------------------------

def coverage(inputs: dict, outputs: dict) -> dict:
    """Score must score every input job exactly once.

    build_scored_jobs silently drops unknown ids, so a hallucinated id shows up
    here as a missing job.
    """
    expected = {j["id"] for j in inputs["job_listings"]}
    got = [m["job_id"] for m in outputs["realistic"]]
    missing = expected - set(got)
    dupes = len(got) - len(set(got))
    return {
        "key": "coverage",
        "score": len(expected - missing) / len(expected),
        "comment": f"missing={sorted(missing)} duplicates={dupes}",
    }


def label_accuracy(outputs: dict, reference_outputs: dict) -> dict:
    """High/low labels vs Score's fit_score."""
    scores = {m["job_id"]: m["fit_score"] for m in outputs["realistic"]}
    checked, wrong = 0, []
    for job_id, label in reference_outputs["labels"].items():
        if label not in ("high", "low"):
            continue
        checked += 1
        fit = scores.get(job_id)
        ok = fit is not None and (fit >= HIGH_MIN if label == "high" else fit < LOW_MAX)
        if not ok:
            wrong.append(f"{job_id}({label})={fit}")
    return {
        "key": "label_accuracy",
        "score": (checked - len(wrong)) / checked if checked else None,
        "comment": f"wrong: {wrong}" if wrong else "all correct",
    }


def stretch_recall(outputs: dict, reference_outputs: dict) -> dict:
    """Share of hand-labelled stretch jobs that Dreamer actually picked."""
    wanted = {j for j, label in reference_outputs["labels"].items() if label == "stretch"}
    picked = {m["job_id"] for m in outputs["stretch"]}
    if not wanted:
        return {"key": "stretch_recall", "score": None}
    return {
        "key": "stretch_recall",
        "score": len(wanted & picked) / len(wanted),
        "comment": f"missed: {sorted(wanted - picked)}",
    }


def dreamer_distinct(outputs: dict) -> dict:
    """Dreamer picks must not be jobs Score already rates as a safe match."""
    scores = {m["job_id"]: m["fit_score"] for m in outputs["realistic"]}
    picks = [m["job_id"] for m in outputs["stretch"]]
    if not picks:
        return {"key": "dreamer_distinct", "score": None, "comment": "no stretch picks"}
    repeats = [j for j in picks if scores.get(j, 0) >= STRONG_MIN]
    return {
        "key": "dreamer_distinct",
        "score": 1 - len(repeats) / len(picks),
        "comment": f"safe matches re-listed: {repeats}",
    }


def main() -> None:
    load_dotenv()
    prefix = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    evaluate(
        target,
        data=DATASET_NAME,
        evaluators=[coverage, label_accuracy, stretch_recall, dreamer_distinct],
        experiment_prefix=prefix,
        num_repetitions=3,
        max_concurrency=1,
    )


if __name__ == "__main__":
    main()
