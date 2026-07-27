"""Static SQL safety checks — the 'smart' guardrail layer.

The read-only DuckDB connection already blocks writes at the engine level.
This adds a check that runs BEFORE execution, so we can (a) give a clear
reason the drafter can learn from, and (b) enforce a LIMIT to cap scans.

Kept separate from the nodes so it's independently unit-testable.
"""
from __future__ import annotations

import sqlglot
from sqlglot import expressions as exp

# Anything that mutates data, schema, or the environment.
FORBIDDEN = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.Merge,
    exp.Copy,      # can write files
    exp.Command,   # generic unparsed commands: ATTACH, PRAGMA, SET, EXPORT ...
)


def check_sql(sql: str, dialect: str = "duckdb", row_cap: int = 1000):
    """Return (ok, reason, safe_sql).

    safe_sql is the (possibly LIMIT-injected) query to run when ok is True.
    """
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except Exception as exc:
        return False, f"could not parse SQL ({exc})", sql

    if len(statements) != 1:
        return False, f"expected exactly one statement, found {len(statements)}", sql

    stmt = statements[0]

    for node in stmt.walk():
        if isinstance(node, FORBIDDEN):
            return False, f"{node.key.upper()} is not allowed — read-only SELECT only", sql

    if stmt.find(exp.Select) is None:
        return False, "only SELECT queries are allowed", sql

    # LIMIT injection: if a top-level SELECT has no LIMIT, add one.
    if isinstance(stmt, exp.Select) and stmt.args.get("limit") is None:
        stmt = stmt.limit(row_cap)

    return True, "safe read-only SELECT", stmt.sql(dialect=dialect)
