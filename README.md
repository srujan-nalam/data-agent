# Data Analyst Agent

**A self-correcting, multi-dataset SQL analyst agent that reasons over real data — live, streamed, and traced.**

Ask it a plain-English question about any dataset. It discovers the real schema, drafts read-only SQL, validates it for safety, runs it, critiques its own answer, retries when it's wrong, and explains the result — all visible in real time in the browser.

**🔗 Live demo:** *deployed on [Railway](https://railway.app) — add your URL here*

```
schema_inspector → planner → drafter → validator → executor → critic → summarizer
                                 ▲          │                     │
                                 └──────────┴────── retry ────────┘
```

---

## Why this project

Most "AI agent" demos are one LLM call wrapped in a chat box. This is built the way a team would actually need to ship and operate an agent that touches real data — with layered safety, self-correction, evals, observability, and cost controls, not just a happy-path demo.

---

## Features

- **Multi-node reasoning graph (LangGraph)** — seven independently testable nodes (schema discovery, planning, SQL drafting, validation, execution, critique, summarization) wired as a real graph with two conditional retry loops, not a fixed chain
- **Self-correcting SQL generation** — when a draft fails (wrong dialect, hallucinated column, mismatched filter value), the specific failure is fed back to the model for a fix, escalating from Sonnet to Opus after repeated misses
- **Result critique, not just error handling** — SQL that *runs* isn't SQL that's *right*; a dedicated critic step inspects results for empty sets, zero-value aggregates, and implausible numbers and triggers a retry
- **Layered safety guardrails** — a `sqlglot`-based validator blocks any query that isn't a single read-only `SELECT` (no DROP/DELETE/UPDATE/INSERT/ATTACH/multi-statement injection), backed by a read-only database connection that blocks writes at the engine level
- **Memory** — a schema cache avoids redundant introspection, and a query library remembers successful `question → SQL` pairs as few-shot examples for future questions
- **Multi-dataset, real ingestion** — curated datasets ship built-in; users can upload a CSV, paste a direct CSV/Parquet URL (with SSRF guards + size caps), or one-click a few working public sample datasets — schema is discovered at runtime with zero hardcoded assumptions
- **Cost-aware model routing** — cheap model for planning/critique/summarizing, a stronger model only for the hard SQL-drafting step, further escalation only after repeated failure, plus a retry cap and a per-IP rate limiter on the public endpoint
- **Live streaming UI** — FastAPI + Server-Sent Events stream every reasoning step to a browser that renders a live node-flow graph (lighting up in real time, including retry loops firing), a step-by-step reasoning ledger, a live LangSmith trace panel, and dataset-aware example questions generated from the actual loaded schema
- **Full observability** — every run is auto-traced to LangSmith via LangGraph's native instrumentation: per-node latency, token counts, and exact prompts/completions, browsable as a tree that mirrors the graph
- **Real eval harness** — a golden test set covering every failure family (happy path, dialect errors, value-mismatch recovery, guardrail blocks), scored against reference SQL, reporting execution success, answer correctness, retry-recovery rate, latency, and token cost
- **Honest failure handling** — no offline stub, no silent fallback; a missing/invalid API key or exhausted credits is classified and surfaced as a clear popup, never a confidently wrong answer
- **Live-only architecture** — deliberately no fallback that could quietly serve fake data; a real error beats a fake answer

---

## Tech stack

| Layer | Technology |
|---|---|
| Agent orchestration | **LangGraph** — stateful graph with conditional retry loops |
| LLM | **Anthropic Claude** — Haiku 4.5 / Sonnet 4.6 / Opus 4.8, routed by task difficulty |
| SQL safety | **sqlglot** — AST-level parsing and validation |
| Data warehouse | **DuckDB** — embedded, read-only enforced at the connection level |
| Backend API | **FastAPI** + **Server-Sent Events** for live streaming |
| Server | **Uvicorn** |
| Validation | **Pydantic** |
| Observability | **LangSmith** — automatic per-node tracing |
| Frontend | Vanilla **HTML/CSS/JS** — SSE client, live SVG node graph, no framework overhead |
| Config | **python-dotenv** |
| Containerization | **Docker** |
| Hosting | **Railway** (backend + service), source on **GitHub** |
| Language | **Python 3.10+** |

---

## Architecture

```
agent/
  state.py          shared LangGraph state (the working memory)
  llm.py             single model choke-point, routing, live error classification
  guardrails.py      sqlglot-based SQL safety checks
  memory.py           schema cache + query library
  observability.py   LangSmith tracing config
  graph.py            the full graph: nodes, edges, retry loops
  nodes/              schema · planner · drafter · validator · executor · critic · summarizer
data/
  warehouse.py        read-only DuckDB access (writes blocked at engine level)
  registry.py          multi-dataset resolver: curated, uploaded, or loaded by URL
service/
  app.py               FastAPI: SSE streaming, upload, URL loading, LangSmith panel
  static/index.html    live showcase UI
evals/
  golden_set.jsonl     test cases across every failure family
  run_evals.py          scores the agent and reports the numbers
scripts/
  ingest.py             builds the curated datasets
Dockerfile               container build for Railway
run.py                    CLI entry point
smoke_test.py              one-command live end-to-end proof
```

---

## Quickstart

```bash
git clone <this-repo>
cd data-agent
cp .env.example .env                     # add ANTHROPIC_API_KEY (+ LangSmith keys)
pip install -e .
python scripts/ingest.py --synthetic     # builds nyc_taxi + ecommerce datasets
python smoke_test.py                     # proves the full live pipeline works
python -m uvicorn service.app:app --port 8000
```

Open `http://localhost:8000` — pick a dataset, click an example question, and watch the pipeline light up live.

CLI:

```bash
python run.py "How many trips are there?"
python run.py --dataset ecommerce "total revenue by category"
```

---

## Deployment (Railway + GitHub)

This project is deployed as a **Docker container on Railway**, built directly from this **GitHub** repository:

1. **Push to GitHub** — the repo includes a `Dockerfile` that installs dependencies and bakes in the curated datasets at build time
2. **Connect the GitHub repo to Railway** — Railway auto-detects the `Dockerfile` and builds the container on every push
3. **Set environment variables in Railway's dashboard**:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   LANGSMITH_TRACING=true
   LANGSMITH_API_KEY=lsv2_...
   LANGSMITH_PROJECT=data-agent
   RATE_LIMIT_PER_MIN=20
   ```
4. **Railway exposes a public URL** automatically — the FastAPI service listens on `0.0.0.0:8000`, matching Railway's expected container port
5. **Every push to `main` redeploys automatically** — GitHub → Railway CI/CD, no manual steps

Full local verification steps — LangSmith trace to browser to CLI — are in `RUNBOOK.md`.

---

## Model routing

| Step | Model | Why |
|---|---|---|
| Plan, critique, summarize | `claude-haiku-4-5-20251001` | cheap, fast, easy steps |
| SQL drafting | `claude-sonnet-4-6` | the hard step |
| Escalation on repeated failure | `claude-opus-4-8` | last resort |

All routing lives in `agent/llm.py` — one file to change.

---

## Why this is production-grade, not a demo

- **Fails safely, in layers** — the read-only DB connection, the `sqlglot` validator, the retry cap, and the rate limiter each independently block a different failure mode; no single guard is load-bearing alone
- **Knows "ran" ≠ "right"** — the critic step caught a real bug during development: a query that silently returned zero rows from a value mismatch (`'credit'` vs `'card'`) — the exact class of confidently-wrong answer that erodes trust in an agent
- **Measured, not just demoed** — a golden eval set scores every failure family against reference SQL, so every prompt or graph change can be checked for regressions before shipping
- **Observable end to end** — every run, CLI or live, is traced to LangSmith at the node level; "we don't know why it broke" isn't a failure mode this system has
- **Cost is a first-class constraint** — routed models, a retry cap, and a rate limiter, not an unbounded token bill
- **Genuinely general** — proven live against real public datasets it never saw during development (weather, market, births records), not a fixture-fitted demo

---

## Roadmap

- [ ] Swap DuckDB for MotherDuck for a fully hosted warehouse
- [ ] RAG upgrade — the query library's keyword retrieval is architected behind a `retrieve_similar()` interface, ready to swap for embeddings
- [ ] Connect-your-own live database — the highest security surface, deliberately built last

---

## Author

**Srujan Nalam** · srujan.nalam@gmail.com

Built to demonstrate production AI engineering — agent architecture with real safety boundaries, proper instrumentation, honest evaluation, and cost/reliability as design constraints from day one, not afterthoughts.
