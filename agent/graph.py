"""Agent graph: safety gate + self-correction loops + memory.

    schema_inspector -> planner -> drafter -> validator --(safe)--> executor
                                     ^          |                     |
                                     |       (unsafe)              critic
                                     +----------+--(retry)------------+
                                                |                     |
                                             (fail)               (ok/give up)
                                                v                     v
                                            summarizer <------------- +

build_agent takes:
  get_warehouse(dataset_id) -> Warehouse   (multi-dataset resolver)
  llm                                        (model interface)
  memory                                     (schema cache + query library)
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from .llm import LLM
from .nodes import (
    make_critic, make_drafter, make_executor, make_planner,
    make_schema_inspector, make_summarizer, make_validator,
)
from .state import AgentState


def _retries_left(state: dict) -> bool:
    return len(state.get("attempts", [])) < state.get("max_retries", 3)


def route_after_validator(state: dict) -> str:
    if state["validation"]["ok"]:
        return "run"
    return "retry" if _retries_left(state) else "fail"


def route_after_critic(state: dict) -> str:
    if state["critique"]["verdict"] == "ok":
        return "answer"
    return "retry" if _retries_left(state) else "answer"


def build_agent(get_warehouse, llm: LLM, memory=None):
    cache = memory.schema if memory else None
    library = memory.library if memory else None

    g = StateGraph(AgentState)
    g.add_node("schema_inspector", make_schema_inspector(get_warehouse, cache))
    g.add_node("planner", make_planner(llm))
    g.add_node("drafter", make_drafter(llm, library))
    g.add_node("validator", make_validator())
    g.add_node("executor", make_executor(get_warehouse))
    g.add_node("critic", make_critic(llm))
    g.add_node("summarizer", make_summarizer(llm, library))

    g.set_entry_point("schema_inspector")
    g.add_edge("schema_inspector", "planner")
    g.add_edge("planner", "drafter")
    g.add_edge("drafter", "validator")
    g.add_conditional_edges("validator", route_after_validator,
                            {"run": "executor", "retry": "drafter", "fail": "summarizer"})
    g.add_edge("executor", "critic")
    g.add_conditional_edges("critic", route_after_critic,
                            {"answer": "summarizer", "retry": "drafter"})
    g.add_edge("summarizer", END)
    return g.compile()
