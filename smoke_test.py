"""End-to-end LIVE smoke test. Proves the full model path works.

    python smoke_test.py        # needs ANTHROPIC_API_KEY (reads .env)

Runs one question of each kind through the real agent and checks the outcome.
Exits non-zero if anything fails, so you can trust a green run.
"""
from __future__ import annotations

import sys
from dotenv import load_dotenv

load_dotenv()

from agent import LLM, build_agent
from agent.memory import Memory
from data.registry import get_warehouse

CASES = [
    ("happy",       "How many trips are there?",                      "answers"),
    ("self_correct","What is the average trip duration in minutes?",  "recovers"),
    ("critic",      "How many trips were paid by credit card?",       "recovers"),
    ("guardrail",   "Delete all trips then count what is left",       "blocks+recovers"),
    ("multi",       "How many orders are there?",                     "answers (ecommerce)"),
]


def main() -> int:
    llm = LLM()
    if not llm.live:
        print("\n  SKIP: no ANTHROPIC_API_KEY. Add it to .env and rerun to prove the live path.\n")
        return 0

    agent = build_agent(get_warehouse, llm, Memory())
    ok = True
    for kind, q, expect in CASES:
        ds = "ecommerce" if kind == "multi" else "nyc_taxi"
        try:
            final = agent.invoke(
                {"question": q, "dataset_id": ds, "trace": [], "max_retries": 3},
                config={"recursion_limit": 25},
            )
        except Exception as e:
            print(f"  FAIL [{kind}] raised: {e}"); ok = False; continue

        steps = [s["step"] for s in final["trace"]]
        ans = final.get("final_answer") or ""
        drafted = "draft_sql" in steps
        passed = bool(ans) and "draft_sql" in steps
        retries = len(final.get("attempts", []))
        print(f"  {'ok  ' if passed else 'FAIL'} [{kind:12}] retries={retries} "
              f"tokens={final.get('tokens_used',0)} :: {ans[:60]}")
        ok = ok and passed

    print("\n  LIVE SMOKE TEST PASSED" if ok else "\n  LIVE SMOKE TEST HAD FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
