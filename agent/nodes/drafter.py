"""Drafter: write SQL from the question + the REAL schema.

Phase 4: feeds prior failures back in and escalates the model on repeat misses.
Phase 5: retrieves similar past successful queries from the query library and
offers them as few-shot examples.
"""
from __future__ import annotations

import re

from ..llm import CAPABLE, STRONG, LLM

SYSTEM = (
    "You are the SQL-writing step of a DuckDB data-analyst agent. "
    "Write ONE read-only SELECT query that answers the question. "
    "Use only tables and columns from the provided schema. "
    "Use DuckDB SQL syntax. Always include a sensible LIMIT. "
    "Return ONLY the SQL, no prose, no markdown fences."
)


def _schema_text(schema: dict | None) -> str:
    if not schema:
        return "(no schema)"
    return "\n".join(
        f"{t}: " + ", ".join(f"{c} {ty}" for c, ty in cols) for t, cols in schema.items()
    )


def _clean(sql: str) -> str:
    return re.sub(r"^```(?:sql)?|```$", "", sql.strip(), flags=re.MULTILINE).strip()


def _correction(attempts: list) -> str:
    if not attempts:
        return ""
    last = attempts[-1]
    problem = last.error or last.critique or "unknown problem"
    return (
        f"\n\nYour previous attempt was:\n{last.sql}\n"
        f"It did not work: {problem}\nFix this specific problem."
    )


def _examples(library, dataset_id: str, question: str) -> str:
    if not library:
        return ""
    hits = library.retrieve(dataset_id, question, k=2)
    if not hits:
        return ""
    lines = "\n".join(f"-- {h['question']}\n{h['sql']}" for h in hits)
    return f"\n\nSimilar past queries that worked:\n{lines}"


def make_drafter(llm: LLM, library=None):
    def drafter(state: dict) -> dict:
        q = state["question"]
        ds = state.get("dataset_id", "nyc_taxi")
        schema = state.get("schema")
        attempts = state.get("attempts", [])
        model = CAPABLE if len(attempts) < 2 else STRONG

        prompt = (
            f"Schema:\n{_schema_text(schema)}\n\n"
            f"Question: {q}\n\nPlan: {state.get('plan', '')}"
            f"{_examples(library, ds, q)}{_correction(attempts)}"
        )
        sql = _clean(
            llm.complete(
                system=SYSTEM, prompt=prompt, model=model, max_tokens=500,
                task="draft", ctx={"question": q, "schema": schema, "attempts": attempts},
            )
        )
        tag = f"  [retry {len(attempts)}, {model.split('-')[1]}]" if attempts else ""
        trace = state.get("trace", []) + [{"step": "draft_sql", "detail": sql + tag}]
        return {"draft_sql": sql, "trace": trace}

    return drafter
