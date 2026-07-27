"""Observability wiring.

LangGraph automatically traces every node run to LangSmith when the right env
vars are present. This helper just reports whether tracing is on and sets a
default project name. Set these to enable it (see .env.example):

    LANGSMITH_TRACING=true
    LANGSMITH_API_KEY=...
    LANGSMITH_PROJECT=data-agent   # optional

With them set, every run.py / eval run shows up in the LangSmith UI with the
full step-by-step trace — the same steps you see in the CLI, but clickable,
timed, and with token counts per node.
"""
from __future__ import annotations

import os


def tracing_enabled() -> bool:
    on = os.environ.get("LANGSMITH_TRACING", "").lower() in ("1", "true", "yes")
    has_key = bool(os.environ.get("LANGSMITH_API_KEY"))
    if on and has_key:
        os.environ.setdefault("LANGSMITH_PROJECT", "data-agent")
        return True
    return False
