"""Planner: read the question, decide the rough shape of the answer.

Runs on the CHEAP model — planning is easy and we escalate spend only where
it's needed (the SQL drafting step).
"""
from __future__ import annotations

from ..llm import CHEAP, LLM

SYSTEM = (
    "You are the planning step of a SQL data-analyst agent. "
    "Given a user's question, briefly state which table(s) and what shape of "
    "answer are needed. Do NOT write SQL. Two sentences max."
)


def make_planner(llm: LLM):
    def planner(state: dict) -> dict:
        q = state["question"]
        plan = llm.complete(
            system=SYSTEM,
            prompt=f"Question: {q}",
            model=CHEAP,
            max_tokens=200,
            task="plan",
            ctx={"question": q},
        )
        trace = state.get("trace", []) + [{"step": "plan", "detail": plan.strip()}]
        return {"plan": plan.strip(), "trace": trace}

    return planner
