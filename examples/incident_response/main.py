"""Voice-served incident response demo with supervised LangGraph sub-agent.

Run: uv run python examples/incident_response/main.py
Then open http://localhost:8002 in your browser.

An operator interacts via voice with a LiveAgent that orchestrates a background
LangGraph investigation agent through LiveLink's supervision pipeline.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from livelink import LiveAgent, ToolContext
from livelink.integrations.langchain import LangGraphAdapter
from livelink.supervision.cancellation import CancellationToken
from livelink.supervision.events import EventBus
from livelink.supervision.hitl import InputManager
from livelink.supervision.runtime_events import (
    ExecutionCompleted,
    ExecutionFailed,
    InterruptRequested,
    StepStarted,
    ToolCallCompleted,
    ToolCallStarted,
)
from livelink.supervision.supervise import supervise

from agent import INITIAL_STATE, graph

INSTRUCTIONS = """You are an SRE operations assistant helping an operator manage a production incident.

The current alert is: Elevated 5xx error rate on checkout-service (12.4%, baseline 0.3%).

Your capabilities:
- start_investigation(): Launches an AI agent to investigate the incident using operational tools
- get_status(): Check what the investigation agent has found so far
- check_approval_needed(): See if the agent needs your operator's approval for a mitigation action
- respond_to_approval(decision): Send the operator's decision (approve/deny/feedback)
- cancel_investigation(): Stop the investigation

Workflow:
1. When the operator asks to investigate, call start_investigation()
2. After a few seconds, call get_status() and summarize findings to the operator
3. Keep checking get_status() periodically until the investigation is complete or approval is needed
4. When approval is needed, clearly explain the proposed mitigation to the operator and ask for their decision
5. Use respond_to_approval() with their answer
6. Report the final outcome

Be concise in your spoken responses. Summarize technical details clearly for the operator.
If the operator says "cancel" or "stop", call cancel_investigation().
"""

agent = LiveAgent(
    model="gemini/gemini-2.5-flash-native-audio",
    instructions=INSTRUCTIONS,
    voice="Puck",
)


@agent.tool
async def start_investigation(ctx: ToolContext) -> str:
    """Launch a background AI agent to investigate the current incident."""
    bus = EventBus()
    input_mgr = InputManager(default_timeout=120.0)
    cancel_token = CancellationToken(name="incident")
    adapter = LangGraphAdapter(graph, config={"configurable": {"thread_id": "voice-inc-1"}})

    task = asyncio.create_task(
        supervise(
            adapter,
            INITIAL_STATE,
            event_bus=bus,
            input_manager=input_mgr,
            cancellation_token=cancel_token,
            interrupt_timeout=120.0,
        )
    )

    ctx.session_state["bus"] = bus
    ctx.session_state["input_mgr"] = input_mgr
    ctx.session_state["cancel_token"] = cancel_token
    ctx.session_state["task"] = task

    return (
        "Investigation started. The agent is now analyzing the incident. "
        "Call get_status() to check progress."
    )


@agent.tool
async def get_status(ctx: ToolContext) -> str:
    """Check the current status and findings of the background investigation."""
    bus: EventBus | None = ctx.session_state.get("bus")
    if bus is None:
        return "No investigation running."

    task: asyncio.Task[Any] = ctx.session_state["task"]
    events = bus.history(limit=20)
    lines: list[str] = []

    for event in events:
        if isinstance(event, StepStarted):
            lines.append(f"Step: {event.step_name}")
        elif isinstance(event, ToolCallStarted):
            lines.append(f"Tool called: {event.tool_name}")
        elif isinstance(event, ToolCallCompleted):
            lines.append(f"Tool result: {event.tool_name} ({event.duration_ms:.0f}ms)")
        elif isinstance(event, ExecutionCompleted):
            lines.append(f"Investigation complete: {event.output_summary}")
        elif isinstance(event, ExecutionFailed):
            lines.append(f"Investigation failed: {event.error}")
        elif isinstance(event, InterruptRequested):
            lines.append(f"APPROVAL NEEDED: {event.payload}")

    if task.done():
        exc = task.exception()
        if exc:
            lines.append(f"Background task failed: {exc}")
        else:
            lines.append("Background task finished.")

    return "\n".join(lines) if lines else "Investigation in progress, no events yet."


@agent.tool
async def check_approval_needed(ctx: ToolContext) -> str:
    """Check if the investigation agent needs operator approval for a mitigation action."""
    input_mgr: InputManager | None = ctx.session_state.get("input_mgr")
    if input_mgr is None:
        return "No investigation running."

    pending = input_mgr.pending_requests()
    if pending:
        req = pending[0]
        return (
            f"APPROVAL REQUIRED: {req.question}. Options: approve, deny, or provide feedback text."
        )
    return "No approval needed at this time."


@agent.tool
async def respond_to_approval(ctx: ToolContext, decision: str) -> str:
    """Send the operator's approval decision to the investigation agent.

    Args:
        decision: The operator's decision — "approve", "deny", or feedback text
    """
    input_mgr: InputManager | None = ctx.session_state.get("input_mgr")
    if input_mgr is None:
        return "No investigation running."

    pending = input_mgr.pending_requests()
    if not pending:
        return "No pending approval request to respond to."

    req = pending[0]
    input_mgr.resolve(req.request_id, decision, source="voice")
    return f"Approval resolved with: {decision}. The investigation will continue."


@agent.tool
async def cancel_investigation(ctx: ToolContext) -> str:
    """Cancel the running investigation."""
    cancel_token: CancellationToken | None = ctx.session_state.get("cancel_token")
    if cancel_token is None:
        return "No investigation running."

    cancel_token.cancel("Operator requested cancellation")
    return "Investigation cancelled."


if __name__ == "__main__":
    agent.serve(port=8002)
