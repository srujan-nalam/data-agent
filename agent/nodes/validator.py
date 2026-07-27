"""Validator (Phase 3): the safety gate, runs BEFORE execution.

Parses the drafted SQL and rejects anything that isn't a single read-only
SELECT, and injects a LIMIT. On rejection it records the reason as a failed
attempt so the drafter can learn from it on retry.
"""
from __future__ import annotations

from ..guardrails import check_sql
from ..state import Attempt


def make_validator(row_cap: int = 1000):
    def validator(state: dict) -> dict:
        sql = state.get("draft_sql", "")
        ok, reason, safe_sql = check_sql(sql, row_cap=row_cap)

        trace = state.get("trace", []) + [
            {"step": "validate", "detail": ("ok" if ok else f"BLOCKED: {reason}")}
        ]
        out: dict = {"validation": {"ok": ok, "reason": reason}, "trace": trace}

        if ok:
            out["draft_sql"] = safe_sql          # the LIMIT-injected version
        else:
            # record a failed attempt so the drafter sees why on retry
            out["attempts"] = state.get("attempts", []) + [
                Attempt(sql=sql, error=reason)
            ]
        return out

    return validator
