"""Read-only access to the warehouse.

Phase 1 uses a local DuckDB file. The `read_only=True` connection is the
first line of the guardrail story from the plan: the engine itself refuses
writes, so no prompt-injected DROP/DELETE can land — before we even parse
the SQL (that stricter check arrives in Phase 3).

Swapping DuckDB -> MotherDuck later is just a different connection string,
which is why all warehouse access lives behind this one class.
"""
from __future__ import annotations

from typing import Any

import duckdb


class Warehouse:
    def __init__(self, path: str) -> None:
        self.path = path
        # read_only=True => the connection cannot mutate data at all.
        self.con = duckdb.connect(path, read_only=True)

    def schema(self) -> dict[str, list[tuple[str, str]]]:
        """Discover tables + columns + types. The agent calls this instead
        of ever assuming a column exists."""
        out: dict[str, list[tuple[str, str]]] = {}
        tables = self.con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()
        for (t,) in tables:
            cols = self.con.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = ? ORDER BY ordinal_position",
                [t],
            ).fetchall()
            out[t] = [(c, ty) for c, ty in cols]
        return out

    def run(self, sql: str, row_cap: int = 1000) -> dict[str, Any]:
        """Execute and fetch at most `row_cap` rows. Errors are returned,
        not raised, so the graph can react to them (self-correction later)."""
        try:
            cur = self.con.execute(sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(row_cap)
            return {
                "columns": columns,
                "rows": [list(r) for r in rows],
                "row_count": len(rows),
                "error": None,
            }
        except Exception as exc:
            return {"columns": [], "rows": [], "row_count": 0, "error": str(exc)}
