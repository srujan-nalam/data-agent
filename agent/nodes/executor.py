"""Executor: run the drafted SQL against the read-only warehouse for the
dataset named in state['dataset_id']."""
from __future__ import annotations


def make_executor(get_warehouse, row_cap: int = 1000):
    def executor(state: dict) -> dict:
        ds = state.get("dataset_id", "nyc_taxi")
        sql = state["draft_sql"]
        result = get_warehouse(ds).run(sql, row_cap=row_cap)
        detail = (
            f"error: {result['error']}"
            if result["error"]
            else f"{result['row_count']} row(s)"
        )
        trace = state.get("trace", []) + [{"step": "execute", "detail": detail}]
        return {"result": result, "trace": trace}

    return executor
