"""Summarizer: turn rows into a plain-English answer, and the graceful-failure
endpoint. Phase 5: on a clean successful answer, remember the (question -> SQL)
pair in the query library.
"""
from __future__ import annotations

from ..llm import CHEAP, LLM

SYSTEM = (
    "You are the answer-writing step of a data-analyst agent. "
    "Given the user's question and the query result, write a short, direct "
    "plain-English answer. State the numbers. No preamble."
)


def _result_text(result: dict | None) -> str:
    if not result:
        return "(no result)"
    if result.get("error"):
        return f"Query failed: {result['error']}"
    cols = result.get("columns", [])
    rows = result.get("rows", [])[:20]
    return " | ".join(cols) + "\n" + "\n".join(
        " | ".join(str(c) for c in r) for r in rows
    )


def make_summarizer(llm: LLM, library=None):
    def summarizer(state: dict) -> dict:
        q = state["question"]
        ds = state.get("dataset_id", "nyc_taxi")
        result = state.get("result")
        validation = state.get("validation") or {}
        critique = state.get("critique") or {}

        if not validation.get("ok", True) and not result:
            answer = f"I couldn't run this safely: {validation.get('reason', 'blocked')}."
            trace = state.get("trace", []) + [{"step": "summarize", "detail": answer}]
            return {"final_answer": answer, "trace": trace, "tokens_used": llm.tokens_used}

        answer = llm.complete(
            system=SYSTEM,
            prompt=f"Question: {q}\n\nResult:\n{_result_text(result)}",
            model=CHEAP, max_tokens=300, task="summarize",
            ctx={"question": q, "result": result},
        ).strip()

        # Remember successful queries (clean result, critic satisfied).
        if library and result and not result.get("error") and critique.get("verdict") == "ok":
            library.add(ds, q, state.get("draft_sql", ""))

        if critique.get("verdict") == "suspect":
            answer += f"\n  (note: {critique.get('reason')})"

        trace = state.get("trace", []) + [{"step": "summarize", "detail": answer}]
        return {"final_answer": answer, "trace": trace, "tokens_used": llm.tokens_used}

    return summarizer
