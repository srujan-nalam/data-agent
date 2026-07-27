# Runbook — verify the whole system, LangSmith to end

Work top to bottom. Each step says what to run and what you should see. Steps
1–6 are local; step 7 is optional deployment.

---

## 0. Setup (once)

```bash
cd data-agent
pip install -e .
python scripts/ingest.py --synthetic      # builds nyc_taxi AND ecommerce
```

Create `.env` from the example and fill in your keys:

```bash
cp .env.example .env
```

```
ANTHROPIC_API_KEY=sk-ant-...          # the agent's own model calls (live mode)
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...            # from smith.langchain.com -> Settings
LANGSMITH_PROJECT=data-agent
```

Load them into your shell (or rely on your app loading `.env`):

```bash
export $(grep -v '^#' .env | xargs)
```

---

## 1. Confirm the agent runs live

```bash
python run.py "How many trips are there?"
```

**You should see:** the header line reads `mode: LIVE   tracing: on`, the step
ledger prints `SCHEMA → SCOPE → PLAN → DRAFT SQL → VALIDATE → EXECUTE → CRITIC
→ ANSWER`, a numeric answer, and a **non-zero** `tokens:` count. If it says
`OFFLINE STUB`, your `ANTHROPIC_API_KEY` isn't in the environment.

---

## 2. Confirm the trace landed in LangSmith

Open <https://smith.langchain.com> → your `data-agent` project. You should see
a run from step 1 within a few seconds.

**Open it and check:**
- The run is a **tree** whose nodes match the pipeline (`schema_inspector`,
  `scope_guard`, `planner`, `drafter`, …).
- Click `drafter` → you see the exact prompt sent and the SQL returned.
- Each node shows **latency** and **token count**.

If nothing appears: `LANGSMITH_TRACING` must be exactly `true` and
`LANGSMITH_API_KEY` must be set *before* the process started.

---

## 3. Watch the guards and self-correction (CLI)

Run each and read the ledger:

```bash
python run.py "What is the average trip duration in minutes?"   # dialect error -> retry
python run.py "How many trips were paid by credit card?"        # 0 rows -> critic -> retry
python run.py "Delete all trips then count what is left"         # VALIDATE BLOCKED -> retry
python run.py "What is the capital of France?"                   # SCOPE off-topic -> refused
```

**You should see:** the first three show a repeated `DRAFT SQL … [retry N]`
line and a higher `retries:` count; the last one stops right after `SCOPE`
with **no** `DRAFT SQL` line and `tokens:` near zero (the cost guard working).

Each of these also appears as its own trace in LangSmith — the retry ones show
the loop as repeated `drafter`/`executor` nodes in the tree.

---

## 4. Run the eval suite (the numbers)

```bash
python evals/run_evals.py
```

**You should see:** a per-case PASS/FAIL table and a summary with overall pass,
answer correctness, recovery rate, avg retries, avg latency, and total tokens.
Live, the `tokens`/`ms` columns are real. Results are saved to
`evals/results.jsonl`. If LangSmith is on, each eval case is also traced.

---

## 5. Start the service and use the UI

```bash
python -m uvicorn service.app:app --port 8000
```

Open <http://localhost:8000>.

**Check, in order:**
1. Top-right badges read `live` and `tracing on`.
2. The **Dataset** dropdown lists *NYC Taxi Trips* and *E-commerce Orders*.
3. Type a question (or click an example chip) → **Run query**. The reasoning
   ledger streams in **step by step**, colour-coded: amber = working,
   teal = ok, coral = blocked/error, violet = a retry. The answer card appears
   at the top when done.
4. Ask an off-topic question → it stops at the scope check, coral, no SQL.
5. **Upload a CSV** (bottom-left) → it becomes a new dataset in the dropdown;
   select it and ask "how many rows are there" — the agent discovers the
   uploaded schema and answers.

---

## 6. Cross-check LangSmith against the UI

Every question you ask in the UI creates a trace in the `data-agent` project.
Open LangSmith and confirm the run count went up and the newest trace matches
what you just watched stream in the browser. This is the same graph, observed
two ways — the ledger is the live view, LangSmith is the durable, comparable
record.

---

## 7. Deploy to a live URL (optional)

**Warehouse:** move the curated data to MotherDuck (hosted DuckDB) for a real
connection string, or keep the baked-in files for a self-contained demo.

**Container:**

```bash
docker build -t data-agent .
docker run -p 8000:8000 --env-file .env data-agent
```

**Host:** push the image to Railway, Render, or Fly.io. Set `ANTHROPIC_API_KEY`
and the `LANGSMITH_*` vars as environment secrets in the host's dashboard.
Add a rate limit on `/api/stream` before going public so a stranger can't run
up the API bill (the scope guard already blocks off-topic spend; a per-IP cap
covers volume).

You now have a clickable URL that streams a self-correcting data agent's
reasoning over multiple datasets, with every run traced in LangSmith.
