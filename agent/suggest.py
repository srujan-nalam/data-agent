"""Generate a few sample questions tailored to a dataset's real schema.

Deterministic (no model call): looks at column types and names and proposes
sensible analytics questions. Falls back to generic ones if the schema is thin.
"""
from __future__ import annotations


def _classify(cols):
    nums, cats, dates, text = [], [], [], []
    for name, typ in cols:
        t = (typ or "").upper()
        if any(k in t for k in ("INT", "DOUBLE", "DECIMAL", "FLOAT", "REAL", "NUMERIC", "BIGINT")):
            nums.append(name)
        elif any(k in t for k in ("DATE", "TIME")):
            dates.append(name)
        elif "BOOL" in t:
            cats.append(name)
        else:
            (cats if name.lower() in ("status", "category", "type", "payment_type",
                                      "weather", "region", "state") else text).append(name)
    return nums, cats, dates, text


def suggest_questions(schema: dict, limit: int = 5) -> list[str]:
    if not schema:
        return ["How many rows are there?"]
    table = next(iter(schema))
    cols = schema[table]
    nums, cats, dates, text = _classify(cols)
    low = table.rstrip("s")

    q = [f"How many {table} are there?"]
    if cats:
        q.append(f"How many {table} are there for each {cats[0]}?")
    if nums:
        q.append(f"What is the average {nums[0]}?")
    if nums and cats:
        q.append(f"What is the total {nums[0]} by {cats[0]}?")
    if len(nums) >= 2:
        q.append(f"Which {low} has the highest {nums[1]}?")
    if dates:
        q.append(f"How many {table} are there per month based on {dates[0]}?")
    if cats and len(q) < limit:
        q.append(f"Which {cats[0]} appears most often?")
    # de-dupe, keep order, cap
    seen, out = set(), []
    for item in q:
        if item not in seen:
            seen.add(item); out.append(item)
    return out[:limit]
