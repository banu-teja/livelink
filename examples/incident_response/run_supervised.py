"""Run the incident response agent WITH RelayKit supervision — the 'after' experience.

Same graph. Same agent. Zero modifications. Just wrapped in supervise().
Run: uv run python examples/incident_response/run_supervised.py
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from livelink.integrations.langchain import LangGraphAdapter
from livelink.supervision.cancellation import CancellationToken
from livelink.supervision.events import EventBus
from livelink.supervision.hitl import InputManager
from livelink.supervision.runtime_events import (
    ExecutionCancelled,
    ExecutionCompleted,
    ExecutionFailed,
    ExecutionStarted,
    InterruptRequested,
    InterruptResolved,
    StepStarted,
    ToolCallCompleted,
    ToolCallFailed,
    ToolCallStarted,
)
from livelink.supervision.supervise import supervise

from agent import INITIAL_STATE, graph


def format_event(event: object) -> str | None:
    """Format a RuntimeEvent for terminal display."""
    if isinstance(event, ExecutionStarted):
        return f"\n{'=' * 60}\n=== Incident Response (Supervised with RelayKit) ===\n{'=' * 60}"
    if isinstance(event, StepStarted):
        return f"  -> Step: {event.step_name}"
    if isinstance(event, ToolCallStarted):
        return f"  [tool] Calling: {event.tool_name}({event.arguments_summary[:60]})"
    if isinstance(event, ToolCallCompleted):
        return f"  [done] {event.tool_name} returned ({event.duration_ms:.0f}ms)"
    if isinstance(event, ToolCallFailed):
        return f"  [fail] {event.tool_name} failed: {event.error}"
    if isinstance(event, InterruptRequested):
        return f"\n  [pause] APPROVAL REQUIRED: {event.payload}"
    if isinstance(event, InterruptResolved):
        return f"  [resume] Resolved: {event.resolution}"
    if isinstance(event, ExecutionCompleted):
        return f"\n[completed] Done ({event.duration_ms:.0f}ms)"
    if isinstance(event, ExecutionFailed):
        return f"\n[failed] {event.error}"
    if isinstance(event, ExecutionCancelled):
        return "\n[cancelled] Execution cancelled by operator"
    return None


async def handle_approvals(input_mgr: InputManager, cancel_token: CancellationToken) -> None:
    """Background task: prompt the operator when approvals are pending."""
    while not cancel_token.is_cancelled:
        await asyncio.sleep(0.5)
        pending = input_mgr.pending_requests()
        if not pending:
            continue
        req = pending[0]
        print("\n" + "=" * 60)
        print("OPERATOR DECISION REQUIRED")
        print(f"Context: {req.context}")
        print("Options: approve | deny | <feedback text> | cancel")
        print("=" * 60)
        answer = await asyncio.get_event_loop().run_in_executor(None, input, "> ")
        if answer.strip().lower() == "cancel":
            cancel_token.cancel("Operator cancelled")
        else:
            input_mgr.resolve(req.request_id, answer.strip(), source="text")


async def main() -> None:
    config = {"configurable": {"thread_id": "incident-demo-1"}}
    adapter = LangGraphAdapter(graph, config=config)
    bus = EventBus()
    input_mgr = InputManager(default_timeout=120.0, event_bus=bus)
    cancel_token = CancellationToken(name="incident-response")

    bus.subscribe_all(lambda ev: (msg := format_event(ev)) and print(msg))
    approval_task = asyncio.create_task(handle_approvals(input_mgr, cancel_token))

    try:
        result = await supervise(
            adapter,
            INITIAL_STATE,
            event_bus=bus,
            input_manager=input_mgr,
            cancellation_token=cancel_token,
            interrupt_timeout=120.0,
        )
        print("\n--- Supervised Run Result ---")
        print(f"Outcome: {result.stopped_reason}")
        print(f"Interrupts handled: {result.interrupts_handled}")
        print(f"Total duration: {result.duration_ms:.0f}ms")
        print("\n--- What supervision provided (vs standalone) ---")
        print("  - Real-time visibility into every step and tool call")
        print("  - Human approval gate: deny, redirect, or cancel at any point")
        print("  - Cooperative cancellation (operator typed 'cancel')")
        print("  - Full audit trail with timestamps on every event")
        print("  - No auto-approve: operator made a real decision")
    finally:
        cancel_token.cancel(reason="run complete")
        approval_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await approval_task


if __name__ == "__main__":
    asyncio.run(main())
