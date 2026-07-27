"""Ask the agent a question from the command line.

    python run.py "How many trips are there?"
    python run.py --dataset ecommerce "total revenue by category"

No ANTHROPIC_API_KEY -> offline stub mode. Set it for live answers.
"""
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import argparse
import os

from agent import LLM, build_agent
from agent.llm import LLMError
from agent.memory import Memory
from agent.observability import tracing_enabled
from data.registry import get_warehouse

STEP_LABEL = {
    "draft_sql": "DRAFT SQL", "validate": "VALIDATE ", "execute": "EXECUTE  ",
    "critic": "CRITIC   ", "summarize": "ANSWER   ",
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("question", nargs="*")
    p.add_argument("--dataset", default="nyc_taxi")
    args = p.parse_args()
    question = " ".join(args.question) or "How many trips are there?"

    llm = LLM()
    if not llm.live:
        print("\n  This agent is live-only. Add ANTHROPIC_API_KEY to a .env file"
              "\n  (copy .env.example) or export it, then rerun.\n")
        return
    memory = Memory()
    agent = build_agent(get_warehouse, llm, memory)

    print(f"\n  question : {question}")
    print(f"  dataset  : {args.dataset}")
    print(f"  mode     : {'LIVE' if llm.live else 'OFFLINE STUB'}"
          f"   tracing: {'on' if tracing_enabled() else 'off'}\n  " + "-" * 62)

    try:
        final = agent.invoke(
            {"question": question, "dataset_id": args.dataset, "trace": [], "max_retries": 3},
            config={"recursion_limit": 25},
        )
    except LLMError as e:
        print(f"\n  {e.user_message}\n")
        return
    for step in final["trace"]:
        label = STEP_LABEL.get(step["step"], step["step"])
        detail = step["detail"].replace("\n", "\n  " + " " * 12)
        print(f"  {label} | {detail}")
    print("  " + "-" * 62)
    print(f"\n  ANSWER: {final.get('final_answer')}")
    print(f"  retries: {len(final.get('attempts', []))}   tokens: {final.get('tokens_used', 0)}\n")


if __name__ == "__main__":
    main()
