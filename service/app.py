"""FastAPI service: streams the agent's reasoning to the browser over SSE.

    python -m uvicorn service.app:app --port 8000

LIVE ONLY. Loads .env, requires ANTHROPIC_API_KEY. Surfaces credit/key errors
to the UI as a popup. Exposes live LangSmith run data when tracing is on.
"""
from __future__ import annotations

import json
import os
import tempfile
import time

from dotenv import load_dotenv

load_dotenv()  # read .env before anything inspects the environment

from fastapi import FastAPI, File, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from agent import LLM, build_agent
from agent.llm import CONTACT, LLMError
from agent.memory import Memory
from agent.observability import tracing_enabled
from data.registry import get_warehouse, list_datasets, register_upload, register_url

STATIC = os.path.join(os.path.dirname(__file__), "static")
PROJECT = os.environ.get("LANGSMITH_PROJECT", "data-agent")

app = FastAPI(title="Data Analyst Agent")

# ---- simple per-IP rate limit on the streaming endpoint ----
# Protects the API key from being drained by rapid-fire requests.
_RATE_MAX = int(os.environ.get("RATE_LIMIT_PER_MIN", "20"))
_hits: dict[str, list] = {}


def _rate_ok(ip: str) -> bool:
    now = time.time()
    window = [t for t in _hits.get(ip, []) if now - t < 60]
    if len(window) >= _RATE_MAX:
        _hits[ip] = window
        return False
    window.append(now)
    _hits[ip] = window
    return True


_llm = LLM()
_memory = Memory()
_agent = build_agent(get_warehouse, _llm, _memory)


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/datasets")
def datasets():
    return {
        "datasets": list_datasets(),
        "configured": _llm.live,
        "tracing": tracing_enabled(),
        "contact": CONTACT,
    }


# ---------------- dataset-aware example questions ----------------
def _suggest_questions(schema: dict | None, wh=None) -> list[str]:
    """Build example questions from the dataset's REAL schema, so the chips
    fit whatever dataset (curated, uploaded, or fetched by URL) is selected.
    Skips id-like columns and only groups by categoricals with sane
    cardinality (2-50 distinct values) when a warehouse is available to check.
    """
    if not schema:
        return ["How many rows are there?"]
    table, cols = next(iter(schema.items()))

    def is_id(name: str) -> bool:
        n = name.lower()
        return n == "id" or n.endswith("_id") or n.endswith("id")

    def is_num(t: str) -> bool:
        t = t.upper()
        return any(k in t for k in ("INT", "DOUBLE", "DECIMAL", "FLOAT", "REAL", "NUMERIC", "BIGINT"))

    def is_cat(t: str) -> bool:
        return "CHAR" in t.upper() or t.upper() in ("TEXT", "BOOLEAN")

    def is_date(t: str) -> bool:
        return any(k in t.upper() for k in ("DATE", "TIMESTAMP", "TIME"))

    nums = [c for c, t in cols if is_num(t) and not is_id(c)]
    dates = [c for c, t in cols if is_date(t)]

    cats = []
    for c, t in cols:
        if not (is_cat(t) and not is_id(c)):
            continue
        if wh is not None:
            try:
                nd = wh.run(f'SELECT COUNT(DISTINCT "{c}") FROM "{table}"')["rows"][0][0]
                if 2 <= nd <= 50:
                    cats.append(c)
            except Exception:
                cats.append(c)
        else:
            cats.append(c)

    h = lambda c: c.replace("_", " ").strip()
    qs = ["How many rows are there?"]
    if nums:
        qs.append(f"What is the average {h(nums[0])}?")
    if cats:
        qs.append(f"How many rows per {h(cats[0])}?")
    if nums and cats:
        qs.append(f"What is the average {h(nums[0])} by {h(cats[0])}?")
    if len(nums) > 1:
        qs.append(f"What is the maximum {h(nums[1])}?")
    if dates:
        qs.append(f"How many rows by month of {h(dates[0])}?")
    elif len(cats) > 1:
        qs.append(f"Which {h(cats[1])} is most common?")
    # Backfill with safe generic questions if the schema was sparse, so
    # every dataset (including a thin 2-column upload) still gets 5.
    fallbacks = [
        "What are the first 10 rows?",
        f"What is the minimum {h(nums[0])}?" if nums else "How many distinct values are there in each column?",
        "Are there any missing values?",
    ]
    for f in fallbacks:
        if len(qs) >= 5:
            break
        if f not in qs:
            qs.append(f)
    return qs[:5]


@app.get("/api/suggestions")
def suggestions(dataset: str = Query("nyc_taxi")):
    try:
        wh = get_warehouse(dataset)
        schema = wh.schema()
    except Exception:
        wh, schema = None, None
    return {"suggestions": _suggest_questions(schema, wh)}


@app.get("/api/stream")
def stream(request: Request, q: str = Query(...), dataset: str = Query("nyc_taxi")):
    client_ip = request.client.host if request.client else "unknown"

    def gen():
        if not _rate_ok(client_ip):
            yield _sse({"step": "error", "kind": "rate", "contact": CONTACT,
                        "detail": "You're sending questions too quickly. Please wait a minute and try again."})
            yield "event: done\ndata: {}\n\n"
            return
        if not _llm.live:
            yield _sse({"step": "error", "kind": "no_key", "contact": CONTACT,
                        "detail": f"The agent isn't configured with an API key. Please contact {CONTACT}."})
            yield "event: done\ndata: {}\n\n"
            return
        state = {"question": q, "dataset_id": dataset, "trace": [], "max_retries": 3}
        seen = 0
        try:
            for chunk in _agent.stream(state, stream_mode="updates",
                                       config={"recursion_limit": 25}):
                for _node, update in chunk.items():
                    trace = update.get("trace")
                    if trace and len(trace) > seen:
                        for step in trace[seen:]:
                            yield _sse(step)
                        seen = len(trace)
                    if update.get("final_answer"):
                        yield _sse({"step": "final", "detail": update["final_answer"],
                                    "tokens": update.get("tokens_used", _llm.tokens_used)})
        except LLMError as e:
            yield _sse({"step": "error", "kind": e.kind, "contact": e.contact,
                        "detail": e.user_message})
        except Exception as e:
            yield _sse({"step": "error", "kind": "other", "contact": CONTACT,
                        "detail": f"Something went wrong: {e}"})
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    suffix = os.path.splitext(file.filename)[1] or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        return register_upload(file.filename, tmp_path)
    finally:
        os.unlink(tmp_path)


class UrlIn(BaseModel):
    url: str
    name: str | None = None


@app.post("/api/load_url")
def load_url(body: UrlIn):
    try:
        return register_url(body.url, body.name)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


# ---------------- LangSmith live panel ----------------
@app.get("/api/langsmith/runs")
def langsmith_runs():
    if not tracing_enabled():
        return {"configured": False, "runs": []}
    out, project_url = [], None
    try:
        from langsmith import Client
        c = Client()
        try:
            project_url = getattr(c.read_project(project_name=PROJECT), "url", None)
        except Exception:
            project_url = None
        try:
            runs = list(c.list_runs(project_name=PROJECT, is_root=True, limit=8))
        except Exception:
            runs = list(c.list_runs(project_name=PROJECT, limit=8))
        for r in runs:
            latency = None
            try:
                if r.end_time and r.start_time:
                    latency = round((r.end_time - r.start_time).total_seconds(), 2)
            except Exception:
                pass
            url = None
            for attempt in (lambda: c.get_run_url(run=r), lambda: c.get_run_url(run_id=r.id)):
                try:
                    url = attempt(); break
                except Exception:
                    continue
            out.append({
                "id": str(getattr(r, "id", "")),
                "name": getattr(r, "name", None) or "run",
                "status": getattr(r, "status", None),
                "latency": latency,
                "tokens": getattr(r, "total_tokens", None),
                "url": url,
                "start": r.start_time.isoformat() if getattr(r, "start_time", None) else None,
            })
    except Exception as e:
        return {"configured": True, "runs": [], "project_url": None, "error": str(e)}
    return {"configured": True, "runs": out, "project_url": project_url}
