"""Schema inspector: read the REAL schema so the drafter never hallucinates a
column. Phase 5: cache per dataset so we introspect the warehouse only once.
Multi-dataset: resolves the warehouse from state['dataset_id'].
"""
from __future__ import annotations


def make_schema_inspector(get_warehouse, cache=None):
    def schema_inspector(state: dict) -> dict:
        ds = state.get("dataset_id", "nyc_taxi")

        schema = cache.get(ds) if cache else None
        source = "cache"
        if schema is None:
            schema = get_warehouse(ds).schema()
            if cache:
                cache.set(ds, schema)
            source = "fresh"

        summary = ", ".join(f"{t}({len(cols)} cols)" for t, cols in schema.items())
        trace = state.get("trace", []) + [
            {"step": "schema", "detail": f"[{source}] {summary}"}
        ]
        return {"schema": schema, "trace": trace}

    return schema_inspector
