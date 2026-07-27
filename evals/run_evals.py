"""Run the agent against the golden set and report metrics.

    python evals/run_evals.py

Scores three kinds of case:
  * data (happy/critic/self_correct): agent's result must match a reference SQL
  * guardrail: the agent must block an unsafe draft and recover to a safe answer
  * scope: the agent must refuse an off-topic question before drafting

Reports execution success, answer correctness, recovery rate, average retries,
latency, and token cost — the numbers that show what the guards buy you.

Runs offline (stub) with no key for a mechanics check; set ANTHROPIC_API_KEY
for real accuracy numbers. If LangSmith env vars are set, every run is also
traced to the LangSmith UI.
"""
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import LLM, build_agent
from agent.memory import Memory
from data.registry import get_warehouse
from agent.observability import tracing_enabled

DB_PATH = os.path.join("data", "warehouse.duckdb")
GOLDEN = os.path.join("evals", "golden_set.jsonl")
RESULTS = os.path.join("evals", "results.jsonl")


def _cell(c):
    if isinstance(c, bool):
        return c
    if isinstance(c, float):
        return round(c, 2)
    if isinstance(c, int) or c is None:
        return c
    return str(c)


def _normalize(result: dict | None) -> list:
    rows = (result or {}).get("rows") or []
    return sorted(tuple(_cell(c) for c in row) for row in rows)


def _score(case: dict, final: dict, warehouse) -> tuple[bool, str]:
    kind = case["kind"]
    trace = final.get("trace", [])

    if kind == "scope":
        refused = not final.get("scope", {}).get("on_topic", True)
        drafted = any(s["step"] == "draft_sql" for s in trace)
        return (refused and not drafted), ("refused before drafting" if refused else "did not refuse")

    if kind == "guardrail":
        blocked = any(s["step"] == "validate" and "BLOCKED" in s["detail"] for s in trace)
        result = final.get("result") or {}
        safe = not result.get("error")
        return (blocked and safe), ("blocked then recovered" if blocked else "unsafe SQL not blocked")

    # data case: compare to reference SQL
    ref = get_warehouse('nyc_taxi').run(case["reference_sql"])
    ok = _normalize(final.get("result")) == _normalize(ref)
    return ok, ("matches reference" if ok else "result differs from reference")


def main() -> None:
    llm = LLM()
    if not llm.live:
        print("\n  Evals are live-only. Set ANTHROPIC_API_KEY (see .env.example) first.\n")
        return
    agent = build_agent(get_warehouse, llm, Memory())

    print(f"\n  mode    : {'LIVE' if llm.live else 'OFFLINE STUB'}")
    print(f"  tracing : {'LangSmith ON' if tracing_enabled() else 'off'}\n")
    print(f"  {'id':16} {'kind':13} {'pass':5} {'retries':8} {'ms':>6}  note")
    print("  " + "-" * 74)

    cases = [json.loads(l) for l in open(GOLDEN) if l.strip()]
    rows = []
    for case in cases:
        before = llm.tokens_used
        t0 = time.time()
        final = agent.invoke(
            {"question": case["question"], "dataset_id": "nyc_taxi",
             "trace": [], "max_retries": 3},
            config={"recursion_limit": 25},
        )
        ms = int((time.time() - t0) * 1000)
        passed, note = _score(case, final, None)
        retries = len(final.get("attempts", []))
        tokens = llm.tokens_used - before
        rows.append({"id": case["id"], "kind": case["kind"], "passed": passed,
                     "retries": retries, "ms": ms, "tokens": tokens, "note": note})
        mark = "PASS" if passed else "FAIL"
        print(f"  {case['id']:16} {case['kind']:13} {mark:5} {retries:^8} {ms:>6}  {note}")

    with open(RESULTS, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    # ---- aggregate ----
    n = len(rows)
    passed = sum(r["passed"] for r in rows)
    data_rows = [r for r in rows if r["kind"] in ("happy", "critic", "self_correct")]
    correct = sum(r["passed"] for r in data_rows)
    failed_first = [r for r in rows if r["retries"] > 0]
    recovered = sum(r["passed"] for r in failed_first)
    avg_retries = sum(r["retries"] for r in rows) / n if n else 0
    avg_ms = sum(r["ms"] for r in rows) / n if n else 0
    total_tokens = sum(r["tokens"] for r in rows)

    print("  " + "-" * 74)
    print(f"\n  overall pass       : {passed}/{n}  ({100*passed//n if n else 0}%)")
    print(f"  answer correctness : {correct}/{len(data_rows)} data questions")
    if failed_first:
        print(f"  recovery rate      : {recovered}/{len(failed_first)} "
              f"of first-draft failures recovered")
    print(f"  avg retries        : {avg_retries:.2f}")
    print(f"  avg latency        : {avg_ms:.0f} ms")
    print(f"  total tokens       : {total_tokens}")
    print(f"\n  results written to {RESULTS}\n")


if __name__ == "__main__":
    main()
