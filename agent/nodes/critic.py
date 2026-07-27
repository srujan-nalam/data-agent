"""Critic (Phase 4): the correctness gate, runs AFTER execution.

The executor is happy as long as the SQL *runs* — but a query can run and
still be wrong (0 rows because a literal like 'credit' doesn't match the real
value 'card', or an empty date range). The critic inspects the *result* and
decides: answer, or send it back to the drafter with a reason.

Rule-based checks (error, empty) plus a cheap model judge on non-empty
model sanity-check on non-empty results.
"""
from __future__ import annotations

from ..llm import CHEAP, LLM
from ..state import Attempt

JUDGE_SYSTEM = (
    "You check whether a SQL result plausibly answers a question. "
    "Reply with exactly 'OK' if it looks reasonable, or 'SUSPECT: <reason>' "
    "if the numbers look wrong, empty, or mismatched. Be terse."
)


def make_critic(llm: LLM):
    def critic(state: dict) -> dict:
        result = state.get("result") or {}
        sql = state.get("draft_sql", "")

        rows = result.get("rows", [])
        first = rows[0] if rows else []
        empty_aggregate = (
            len(rows) == 1 and len(first) == 1 and first[0] in (0, 0.0, None)
        )

        if result.get("error"):
            verdict, reason = "bad", f"execution failed: {result['error']}"
        elif result.get("row_count", 0) == 0 or empty_aggregate:
            verdict, reason = "suspect", (
                "result came back empty/zero — a filter value or date range may "
                "not match the actual data (check exact string values)"
            )
        else:
            verdict, reason = "ok", "result is non-empty and ran cleanly"
            # Sanity-check the actual numbers with the cheap model.
            if True:
                cols = result.get("columns", [])
                rows = result.get("rows", [])[:5]
                judgment = llm.complete(
                    system=JUDGE_SYSTEM,
                    prompt=f"Question: {state['question']}\nColumns: {cols}\nRows: {rows}",
                    model=CHEAP,
                    max_tokens=60,
                ).strip()
                if judgment.upper().startswith("SUSPECT"):
                    verdict, reason = "suspect", judgment

        trace = state.get("trace", []) + [
            {"step": "critic", "detail": f"{verdict}: {reason}"}
        ]
        out: dict = {"critique": {"verdict": verdict, "reason": reason}, "trace": trace}

        if verdict != "ok":
            out["attempts"] = state.get("attempts", []) + [
                Attempt(sql=sql, error=result.get("error"), critique=reason)
            ]
        return out

    return critic
