"""Stage 1, Step 5: run the eval question set against ask.py and record results.

Does NOT grade anything automatically - correctness is a human judgment call.
This script's only job is to run every question once and save what came back,
so grading can happen afterward (filling in the grade/retrieval_hit columns)
without re-running - and re-paying for - the LLM calls.
"""

import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from ask import answer  # noqa: E402  (import after sys.path tweak, needs src/ on path)

QUESTIONS_CSV = Path(__file__).parent / "questions.csv"
RESULTS_CSV = Path(__file__).parent / "results.csv"


def run_eval() -> None:
    with open(QUESTIONS_CSV, newline="", encoding="utf-8") as f:
        questions = list(csv.DictReader(f))

    results = []
    for i, q in enumerate(questions, start=1):
        print(f"[{i}/{len(questions)}] {q['question']}")
        result = answer(q["question"])
        tokens = result.get("tokens", {})
        results.append({
            "question": q["question"],
            "expected_answer": q["expected_answer"],
            "expected_source": q["source"],
            "expected_page": q["page"],
            "actual_answer": result["answer"],
            "actual_sources": " | ".join(result["sources"]),
            "tokens_in": tokens.get("in", ""),
            "tokens_out": tokens.get("out", ""),
            "grade": "",          # fill in by hand: correct / partly / wrong
            "retrieval_hit": "",  # fill in by hand: yes / no - was the expected page in the sources?
        })

    # Every row above cost a real API call. If the primary destination is locked
    # (e.g. open in Excel - a PermissionError on Windows) or any other write error
    # occurs, fall back to a timestamped file rather than losing already-paid-for
    # results to an unhandled exception.
    try:
        _write_results(results, RESULTS_CSV)
        print(f"\nSaved {len(results)} results to {RESULTS_CSV}")
    except OSError as e:
        fallback = RESULTS_CSV.with_name(f"results_{int(time.time())}.csv")
        print(f"\nCould not write to {RESULTS_CSV} ({e}). Saving to {fallback} instead.")
        _write_results(results, fallback)
        print(f"Saved {len(results)} results to {fallback} - merge it in manually.")


def _write_results(results: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)


if __name__ == "__main__":
    run_eval()
