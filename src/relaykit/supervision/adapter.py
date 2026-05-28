"""ExecutionAdapter protocol and typed AdapterEvent variants.

Defines the protocol that external orchestrator adapters (LangGraph, Temporal, etc.)
must implement, plus the strongly-typed event stream they emit during execution.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol, Union, runtime_checkable


# ---------------------------------------------------------------------------
# AdapterEvent variants (frozen dataclasses)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LifecycleStartedEvent:
    input_summary: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class LifecycleCompletedEvent:
    output_summary: str
    duration_ms: float
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class LifecycleFailedEvent:
    error: str
    recoverable: bool
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class StepStartedEvent:
    step_name: str
    step_index: int
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class StepCompletedEvent:
    step_name: str
    step_index: int
    duration_ms: float
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class ToolStartedEvent:
    tool_name: str
    call_id: str
    arguments_summary: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class ToolCompletedEvent:
    tool_name: str
    call_id: str
    result_summary: str
    duration_ms: float
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class ToolFailedEvent:
    tool_name: str
    call_id: str
    error: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class InterruptRequestedEvent:
    interrupt_id: str
    payload: Any
    step_name: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class TokenDeltaEvent:
    content: str
    step_name: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class MessageCompleteEvent:
    content: str
    role: str
    step_name: str
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# AdapterEvent union type
# ---------------------------------------------------------------------------

AdapterEvent = Union[
    LifecycleStartedEvent,
    LifecycleCompletedEvent,
    LifecycleFailedEvent,
    StepStartedEvent,
    StepCompletedEvent,
    ToolStartedEvent,
    ToolCompletedEvent,
    ToolFailedEvent,
    InterruptRequestedEvent,
    TokenDeltaEvent,
    MessageCompleteEvent,
]


# ---------------------------------------------------------------------------
# ExecutionAdapter protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ExecutionAdapter(Protocol):
    async def start(self, input: Any) -> AsyncIterator[AdapterEvent]: ...

    async def resume(self, value: Any) -> AsyncIterator[AdapterEvent]: ...

    async def cancel(self) -> None: ...
