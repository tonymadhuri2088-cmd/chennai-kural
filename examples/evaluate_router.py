"""Measures how well the router sorts complaints, on a small labelled test set.

Usage (from the project root):
    python examples/evaluate_router.py
        Uses the keyword classifier only. No model, no internet.

    python examples/evaluate_router.py --llm
        Also runs the local LLM classifier (Ollama with llama3.1 must be running).
        If Ollama is not reachable the router falls back to keywords. The script then
        says so and does NOT report those numbers as LLM results.

    python examples/evaluate_router.py --json results.json
        Also writes every result to a file.

The test set is data/eval_complaints.csv. The complaints were written and labelled by the project
authors. It is small (45 complaints) and it is not independent, so the numbers show how the
router behaves on these examples. They are not proof of how it will behave on real complaints.

The script exits with 2 if the test set is malformed (for example a label that is not a charter
complaint type), so a broken test set cannot pass silently.
"""

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "complaint_tools"))

# pylint: disable=wrong-import-position
from complaintrouter.common import load_charter  # noqa: E402
from complaintrouter.pipeline import run_complaint  # noqa: E402
from complaintrouter.router import route  # noqa: E402

TEST_SET = ROOT / "data" / "eval_complaints.csv"
REQUIRED_COLUMNS = ["id", "group", "text", "expected_type", "expected_urgent"]


def load_test_set(charter: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Read the test set and check every row. Exits with 2 on a malformed file."""
    problems: List[str] = []
    rows: List[Dict[str, Any]] = []
    with open(TEST_SET, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != REQUIRED_COLUMNS:
            sys.exit(f"{TEST_SET.name}: columns must be {REQUIRED_COLUMNS}, found {reader.fieldnames}")
        seen = set()
        for line, row in enumerate(reader, start=2):
            if row["id"] in seen:
                problems.append(f"line {line}: duplicate id {row['id']}")
            seen.add(row["id"])
            if row["expected_type"] not in charter["complaint_types"]:
                problems.append(f"line {line}: {row['expected_type']!r} is not a charter complaint type")
            if row["expected_urgent"] not in ("yes", "no"):
                problems.append(f"line {line}: expected_urgent must be yes or no")
            if len(row["text"].strip()) < 10:
                problems.append(f"line {line}: complaint text is too short")
            row["expected_urgent"] = row["expected_urgent"] == "yes"
            rows.append(row)
    if problems:
        print("The test set is malformed:")
        for problem in problems:
            print("  -", problem)
        sys.exit(2)
    return rows


def evaluate(rows: List[Dict[str, Any]], charter: Dict[str, Any], use_llm: bool) -> List[Dict[str, Any]]:
    """Run every complaint through the router and record what came out."""
    results = []
    for row in rows:
        started = time.perf_counter()
        result = run_complaint(row["text"], None, use_llm=use_llm)
        elapsed_ms = (time.perf_counter() - started) * 1000
        got = result["classification"]
        expected_route = route(row["expected_type"], charter)
        results.append({
            "id": row["id"],
            "group": row["group"],
            "text": row["text"],
            "expected_type": row["expected_type"],
            "got_type": got["complaint_type"],
            "type_ok": got["complaint_type"] == row["expected_type"],
            "expected_urgent": row["expected_urgent"],
            "got_urgent": bool(got["urgent"]),
            "urgent_ok": bool(got["urgent"]) == row["expected_urgent"],
            "flagged_for_review": bool(got["needs_human_review"]),
            "classifier": got["classifier"],
            "route_ok": (result["route"].get("owner") == expected_route.get("owner")
                         and result["route"].get("escalation_key") == expected_route.get("escalation_key")),
            "ms": elapsed_ms,
        })
    return results


def percent(part: int, whole: int) -> str:
    return f"{100 * part / whole:5.1f}%  ({part}/{whole})" if whole else "n/a (0 cases)"


def report(title: str, results: List[Dict[str, Any]]) -> None:
    total = len(results)
    print(f"\n=== {title} ({total} complaints) ===")
    print(f"Complaint type correct        {percent(sum(r['type_ok'] for r in results), total)}")
    print(f"Routing correct (owner + escalation key)  {percent(sum(r['route_ok'] for r in results), total)}")

    urgent = [r for r in results if r["expected_urgent"]]
    caught = sum(r["got_urgent"] for r in urgent)
    flagged = [r for r in results if r["got_urgent"]]
    print(f"Urgent cases caught (recall)  {percent(caught, len(urgent))}")
    print(f"Urgent flags that were right (precision)  {percent(sum(r['expected_urgent'] for r in flagged), len(flagged))}")

    end_to_end = sum(r["type_ok"] and r["urgent_ok"] for r in results)
    print(f"End to end (type and urgency both right)  {percent(end_to_end, total)}")
    print(f"Sent to a human for review    {percent(sum(r['flagged_for_review'] for r in results), total)}")
    wrong = [r for r in results if not r["type_ok"]]
    confident = [r for r in wrong if not r["flagged_for_review"]]
    print(f"Wrong type AND not flagged for review (the risky ones)  {percent(len(confident), total)}")

    print("By group:")
    for group in dict.fromkeys(r["group"] for r in results):
        part = [r for r in results if r["group"] == group]
        print(f"  {group:8s} type correct {percent(sum(r['type_ok'] for r in part), len(part))}")

    times = sorted(r["ms"] for r in results)
    p95 = times[min(len(times) - 1, int(0.95 * len(times)))]
    print(f"Time per complaint: mean {statistics.mean(times):.1f} ms, 95th percentile {p95:.1f} ms")

    if wrong or any(r["expected_urgent"] and not r["got_urgent"] for r in results):
        print("Misses:")
        for r in results:
            notes = []
            if not r["type_ok"]:
                notes.append(f"type {r['got_type']} instead of {r['expected_type']}")
            if r["expected_urgent"] and not r["got_urgent"]:
                notes.append("urgent case NOT marked urgent")
            if notes:
                print(f"  {r['id']} [{r['group']}] {'; '.join(notes)}"
                      f"{'' if r['flagged_for_review'] else ' (not flagged for review)'}")
                print(f"      {r['text'][:110]}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the complaint router on the labelled test set.")
    parser.add_argument("--llm", action="store_true", help="also run the local LLM classifier (needs Ollama)")
    parser.add_argument("--json", metavar="FILE", help="write every result to this file")
    args = parser.parse_args(argv)

    charter = load_charter()
    rows = load_test_set(charter)
    print(f"Test set: {TEST_SET.relative_to(ROOT)}, {len(rows)} complaints written and labelled by the project authors.")
    print("Small and not independent: this shows behaviour on these examples, not on real complaints.")

    output: Dict[str, Any] = {}
    keyword = evaluate(rows, charter, use_llm=False)
    report("Keyword classifier (no model)", keyword)
    output["keyword"] = keyword

    if args.llm:
        llm = evaluate(rows, charter, use_llm=True)
        used = sum(r["classifier"] == "llm" for r in llm)
        if used == 0:
            print("\nThe local LLM was not reachable: every complaint fell back to the keyword classifier.")
            print("Start Ollama (ollama pull llama3.1) and run again. No LLM numbers are reported.")
        else:
            report(f"Local LLM classifier ({used} of {len(llm)} answered by the model, the rest fell back to keywords)", llm)
        output["llm"] = llm

    if args.json:
        Path(args.json).write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nResults written to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
