# Planted data defects

`scripts/dirty_data.py` deliberately introduces these so evals have ground
truth and the showcase can prove the agent copes with real-world mess.

| # | Defect | Where | What a good agent does |
|---|--------|-------|------------------------|
| 1 | Duplicate rows (~1%) | `trips` | De-dupes or flags inflated counts |
| 2 | Nulls in `passenger_count` (~2%) | `trips` | Handles NULLs in aggregates |
| 3 | Timezone drift (+5h on ~10%) | `pickup_datetime` | Notices/normalizes the shift |
| 4 | Mixed casing/whitespace ` Card ` | `payment_type` | Trims + normalizes before grouping |

Add a matching eval case per row in `evals/golden_set.jsonl` (Phase 6).
