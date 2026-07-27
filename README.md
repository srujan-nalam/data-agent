# Data Analyst Agent — Phase 1 (happy path)

A self-correcting, multi-dataset SQL data-analyst agent. This is **Phase 1**:
one thin vertical slice working end-to-end, built to grow into the full system
(guardrails, self-correction loops, evals, observability, a showcase site).

```
schema_inspector → scope_guard → planner → drafter → validator → executor → critic → summarizer
```

The agent takes a plain-English question, discovers the real schema (never
hallucinates a column), drafts read-only SQL, runs it against a DuckDB
warehouse, and answers in plain English — with a full step-by-step trace.

## Quickstart

```bash
pip install -e .                       # or: pip install duckdb sqlglot pydantic langgraph anthropic
python scripts/ingest.py --synthetic   # build a local warehouse (no downloads)
python run.py "How many trips are there?"
python run.py "What is the average trip duration in minutes?"   # watch it self-correct
```

See `DEMO_QUESTIONS.md` for questions that show the self-correction loops in action.


### Real NYC taxi data

```bash
python scripts/ingest.py --real --month 2024-01   # ~50MB Parquet, needs internet
```

## Layout

```
agent/
  state.py          shared LangGraph state (the working memory)
  llm.py            single model choke-point + routing + offline stub
  graph.py          Phase 1 wiring (marks where Phase 3/4 nodes slot in)
  nodes/            planner · schema · drafter · executor · summarizer
data/
  warehouse.py      read-only DuckDB access (writes blocked at engine level)
scripts/
  ingest.py         synthetic or real NYC taxi loader
  dirty_data.py     injects realistic mess (Phase 4+); see DEFECTS.md
run.py              CLI: ask a question, watch the steps
```

## Model routing

| Step | Model | Why |
|------|-------|-----|
| planner, critic, summarizer | `claude-haiku-4-5-20251001` | cheap/fast, easy steps |
| drafter (SQL) | `claude-sonnet-4-6` | the hard step |
| escalation on repeated failure | `claude-opus-4-8` | last resort |

All routing lives in `agent/llm.py` — one file to change.

## Live-only

This agent requires a working `ANTHROPIC_API_KEY` — there is no offline mode.
Put your keys in a `.env` file (copy `.env.example`); the app and CLI load it
automatically via python-dotenv. The UI shows a **live**/**not configured**
badge, streams a live LangSmith panel when tracing is on, and pops a clear
message (with a contact address) if the key is missing or credits run out.

## Run the showcase (service + UI)

```bash
python -m uvicorn service.app:app --port 8000
```

Open <http://localhost:8000>: pick a dataset (or upload a CSV), ask a question,
and watch the agent's reasoning stream in live — each node colour-coded by
status, with SQL and retries visible. Endpoints: `/api/datasets`,
`/api/stream` (SSE), `/api/upload`.

**Full verification steps — LangSmith to end — are in `RUNBOOK.md`.**

## Scope guard (cost protection)

`scope_guard` runs right after the free schema lookup and before any paid model
call. Off-topic questions (trivia, creative writing, coding help) are refused
immediately, so the API key and tokens are never spent answering anything but
data-analysis questions about the loaded dataset. Try:

```bash
python run.py "What is the capital of France?"   # refused, no drafter runs
```

## Evals

```bash
python evals/run_evals.py
```

Runs the agent against `evals/golden_set.jsonl` and reports execution success,
answer correctness (vs a reference SQL), recovery rate, average retries,
latency, and token cost. Offline it checks the mechanics; set
`ANTHROPIC_API_KEY` for real accuracy numbers. Results are written to
`evals/results.jsonl`.

## Observability (LangSmith)

Set these (see `.env.example`) and every run — CLI or eval — is traced to the
LangSmith UI with per-node timing and token counts:

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=data-agent
```

