"""Canonical RuntimeEvent types for external-execution supervision.

Separate domain from SupervisionEvent (voice-session lifecycle).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RuntimeEvent:
    source: str
    run_id: str
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Execution Lifecycle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionStarted(RuntimeEvent):
    input_summary: str = ""


@dataclass(frozen=True)
class ExecutionCompleted(RuntimeEvent):
    output_summary: str = ""
    duration_ms: float = 0.0


@dataclass(frozen=True)
class ExecutionFailed(RuntimeEvent):
    error: str = ""
    recoverable: bool = False


# ---------------------------------------------------------------------------
# Step Progress
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StepStarted(RuntimeEvent):
    step_name: str = ""
    step_index: int = 0


@dataclass(frozen=True)
class StepCompleted(RuntimeEvent):
    step_name: str = ""
    step_index: int = 0
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# Tool Execution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolCallStarted(RuntimeEvent):
    tool_name: str = ""
    call_id: str = ""
    arguments_summary: str = ""


@dataclass(frozen=True)
class ToolCallCompleted(RuntimeEvent):
    tool_name: str = ""
    call_id: str = ""
    result_summary: str = ""
    duration_ms: float = 0.0


@dataclass(frozen=True)
class ToolCallFailed(RuntimeEvent):
    tool_name: str = ""
    call_id: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Interrupts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InterruptRequested(RuntimeEvent):
    interrupt_id: str = ""
    payload: Any = None
    step_name: str = ""


@dataclass(frozen=True)
class InterruptResolved(RuntimeEvent):
    interrupt_id: str = ""
    resolution: Any = None
    wait_duration_ms: float = 0.0


@dataclass(frozen=True)
class InterruptTimedOut(RuntimeEvent):
    interrupt_id: str = ""
    timeout_ms: float = 0.0


@dataclass(frozen=True)
class InterruptCancelled(RuntimeEvent):
    interrupt_id: str = ""
    reason: str = ""


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CancellationRequested(RuntimeEvent):
    reason: str = ""


@dataclass(frozen=True)
class ExecutionCancelled(RuntimeEvent):
    at_step: str | None = None
    clean: bool = False


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenDelta(RuntimeEvent):
    content: str = ""
    step_name: str = ""


@dataclass(frozen=True)
class MessageComplete(RuntimeEvent):
    role: str = ""
    content: str = ""
    step_name: str = ""
