"""Shared state that flows through the LangGraph agent.

The state IS the working memory: each node reads what it needs and writes
its contribution back. `trace` is the human-readable step log the CLI and
(later) the showcase UI replay.
"""
from __future__ import annotations

from typing import Optional, TypedDict

from pydantic import BaseModel


class Attempt(BaseModel):
    """One draft->run cycle. In Phase 1 there's only ever one; the
    self-correction loops in Phase 4 append more."""
    sql: str
    error: Optional[str] = None
    critique: Optional[str] = None


class AgentState(TypedDict, total=False):
    # --- inputs ---
    question: str
    dataset_id: str

    # --- filled in as the graph runs ---
    schema: Optional[dict]        # {table: [(col, type), ...]}
    plan: Optional[str]           # what tables / shape of answer
    draft_sql: Optional[str]
    validation: Optional[dict]    # {"ok": bool, "reason": str}  (Phase 3)
    result: Optional[dict]        # {"columns": [...], "rows": [...], "row_count": int, "error": str|None}
    critique: Optional[dict]      # {"verdict": "ok"|"suspect"|"bad", "reason": str}  (Phase 4)
    final_answer: Optional[str]

    # --- bookkeeping ---
    attempts: list                # list[Attempt]
    tokens_used: int
    trace: list                   # list[dict]  step-by-step log for replay
    max_retries: int              # reliability cap (used from Phase 4 on)
