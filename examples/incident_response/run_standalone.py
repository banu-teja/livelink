"""Run the incident response agent standalone -- the 'before' experience.

No supervision, no visibility, no human oversight. Auto-approves everything.

Run: uv run python examples/incident_response/run_standalone.py
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from langgraph.types import Command

from agent import INITIAL_STATE, graph


def main() -> None:
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    print("=== Incident Response (Standalone - No Supervision) ===")
    print(f"Running agent on: {INITIAL_STATE['alert']}\n")

    start = time.time()

    print("[Agent investigating... no visibility into tool calls or reasoning]\n")
    result = graph.invoke(INITIAL_STATE, config)

    print("Auto-approving mitigation plan (no human oversight)...\n")
    result = graph.invoke(Command(resume="approve"), config)

    elapsed = time.time() - start

    print(f"Final status: {result['status']}")
    print(f"Duration: ~{elapsed:.0f} seconds\n")
    print("What you missed:")
    print("  - Which tools the agent called")
    print("  - What evidence it gathered")
    print("  - The reasoning behind its mitigation choice")
    print("  - The ability to deny, redirect, or ask for more info")


if __name__ == "__main__":
    main()
