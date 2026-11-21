"""Stage 2, Step 7: run the SQL agent eval set and score it automatically.

Unlike Stage 1's eval (ask.py's answers require human judgment), this one can
be graded by code: compare the agent's SQL results against hand-written gold
SQL, run against the same live DuckDB file, rather than against a fixed
expected value. Two different queries can both be right, so results are
compared as sorted, rounded row sets - not the SQL text itself.

"ambiguous" questions have no gold_sql (there's no single correct
interpretation) and are not scored - only recorded for manual review.

Every row below costs real OpenAI calls (one for generate_sql, one for
summarize, times up to MAX_RETRIES+1 on retries). Don't re-run this casually.
"""
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from sql_agent import ask_data, run_sql  # noqa: E402  (import after sys.path tweak, needs src/ on path)

QUESTIONS_CSV = Path(__file__).parent / "sql_questions.csv"
RESULTS_CSV = Path(__file__).parent / "sql_eval_results.csv"


def normalize_rows(rows: list[tuple]) -> list[tuple]:
    """Round floats to 2 decimals and sort, so row order and float noise don't
    cause a false mismatch. Column order still must match between the gold
    and agent queries - this does not reconcile differently-ordered columns."""
    def norm_val(v):
        return round(v, 2) if isinstance(v, float) else v
    return sorted(tuple(norm_val(v) for v in row) for row in rows)


def results_match(gold_sql: str, agent_sql: str) -> bool:
    _, gold_rows = run_sql(gold_sql)
    _, agent_rows = run_sql(agent_sql)
    return normalize_rows(gold_rows) == normalize_rows(agent_rows)


def run_eval() -> None:
    with open(QUESTIONS_CSV, newline="", encoding="utf-8") as f:
        questions = list(csv.DictReader(f))

    results = []
    for i, q in enumerate(questions, start=1):
        print(f"[{i}/{len(questions)}] {q['question']}")
        result = ask_data(q["question"])
        agent_sql = result.get("sql")
        kind = q["kind"]

        refused = agent_sql is None or result.get("blocked", False)
        errored = "error" in result
        execution_match = ""   # "" = not scored (ambiguous, or no SQL ran)
        if kind == "answerable" and agent_sql and not errored:
            try:
                execution_match = results_match(q["gold_sql"], agent_sql)
            except Exception as e:  # gold_sql itself failed, or a mismatch we didn't anticipate
                execution_match = f"ERROR: {e}"

        correct_refusal = ""  # only meaningful for unanswerable/attack
        if kind in ("unanswerable", "attack"):
            correct_refusal = refused

        results.append({
            "question": q["question"],
            "kind": kind,
            "gold_sql": q["gold_sql"],
            "agent_sql": agent_sql or "",
            "agent_answer": result["answer"],
            "attempts": result["attempts"],
            "blocked": result.get("blocked", False),
            "errored": errored,
            "execution_match": execution_match,
            "correct_refusal": correct_refusal,
        })

    try:
        _write_results(results, RESULTS_CSV)
        print(f"\nSaved {len(results)} results to {RESULTS_CSV}")
    except OSError as e:
        fallback = RESULTS_CSV.with_name(f"sql_eval_results_{int(time.time())}.csv")
        print(f"\nCould not write to {RESULTS_CSV} ({e}). Saving to {fallback} instead.")
        _write_results(results, fallback)
        print(f"Saved {len(results)} results to {fallback} - merge it in manually.")

    _print_summary(results)


def _write_results(results: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)


def _print_summary(results: list[dict]) -> None:
    answerable = [r for r in results if r["kind"] == "answerable"]
    refusal_rows = [r for r in results if r["kind"] in ("unanswerable", "attack")]
    scored_for_validity = [r for r in results if r["kind"] in ("answerable", "ambiguous")]

    execution_accuracy = _rate(answerable, lambda r: r["execution_match"] is True)
    valid_sql_rate = _rate(scored_for_validity, lambda r: bool(r["agent_sql"]) and not r["errored"])
    refusal_accuracy = _rate(refusal_rows, lambda r: r["correct_refusal"] is True)
    avg_attempts = sum(r["attempts"] for r in results) / len(results)

    print("\n--- Summary ---")
    print(f"Execution accuracy  (answerable, n={len(answerable)}): {execution_accuracy:.0%}")
    print(f"Valid SQL rate      (answerable+ambiguous, n={len(scored_for_validity)}): {valid_sql_rate:.0%}")
    print(f"Refusal accuracy    (unanswerable+attack, n={len(refusal_rows)}): {refusal_accuracy:.0%}")
    print(f"Average attempts    (all {len(results)} questions): {avg_attempts:.2f}")


def _rate(rows: list[dict], predicate) -> float:
    return sum(1 for r in rows if predicate(r)) / len(rows) if rows else 0.0


if __name__ == "__main__":
    run_eval()
