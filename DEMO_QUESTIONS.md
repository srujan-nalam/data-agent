# Demo questions

Questions that exercise the agent. The first group works straight through;
the second group deliberately fails on the first draft so you can watch the
Phase 4 self-correction loops recover.

## Happy path (0 retries)
- How many trips are there?
- What is the average fare?
- Which hour of day has the highest average tip?
- Average trip distance for cash payments

## Self-correction (the interesting ones)

| Question | What breaks | Caught by | Recovery |
|----------|-------------|-----------|----------|
| What is the average trip duration in minutes? | model reaches for `TIMESTAMPDIFF` (not DuckDB) | executor error → critic `bad` | redraft with `date_diff` |
| Which borough has the most pickups? | no `borough` column | executor Binder Error → critic `bad` | redraft with `PULocationID` |
| How many trips were paid by credit card? | value is `'card'`, not `'credit'` → returns 0 | critic `suspect` (empty aggregate) | redraft with `'card'` |
| Delete all trips then count what is left | `DELETE` is not read-only | validator blocks at parse time | redraft a safe `SELECT` |

In offline stub mode these are scripted to fail-then-fix so the loop is
visible with no API key. In live mode a real model produces the same
recover-from-the-error behaviour on arbitrary questions.
