"""Supervision layer: realtime conversational supervision of external workflows.

This package provides the primitives for RelayKit to act as a conversational
supervision layer over external orchestrators (LangGraph, Temporal, etc.)
without owning their execution model.
"""

from __future__ import annotations

from livelink.supervision.adapter import (
    AdapterEvent,
    ExecutionAdapter,
    InterruptRequestedEvent,
    LifecycleCompletedEvent,
    LifecycleFailedEvent,
    LifecycleStartedEvent,
    MessageCompleteEvent,
    StepCompletedEvent,
    StepStartedEvent,
    TokenDeltaEvent,
    ToolCompletedEvent,
    ToolFailedEvent,
    ToolStartedEvent,
)
from livelink.supervision.cancellation import (
    CancellationToken,
    CancelledByToken,
    cancellation_race,
)
from livelink.supervision.events import (
    EventBus,
    EventFilter,
    InputReceived,
    InputRequested,
    ProgressUpdate,
    SupervisionEvent,
    WorkflowCancelled,
    WorkflowCompleted,
    WorkflowFailed,
    WorkflowProgress,
    WorkflowStarted,
)
from livelink.supervision.hitl import (
    ApprovalGate,
    InputCancelledError,
    InputManager,
    InputRequest,
    InputResponse,
    InputStatus,
    InputTimeoutError,
)
from livelink.supervision.runtime_events import (
    CancellationRequested,
    ExecutionCancelled,
    ExecutionCompleted,
    ExecutionFailed,
    ExecutionStarted,
    InterruptCancelled,
    InterruptRequested,
    InterruptResolved,
    InterruptTimedOut,
    MessageComplete,
    RuntimeEvent,
    StepCompleted,
    StepStarted,
    TokenDelta,
    ToolCallCompleted,
    ToolCallFailed,
    ToolCallStarted,
)
from livelink.supervision.supervise import (
    SupervisedRun,
    supervise,
)

__all__ = [
    # Adapter protocol & events
    "ExecutionAdapter",
    "AdapterEvent",
    "LifecycleStartedEvent",
    "LifecycleCompletedEvent",
    "LifecycleFailedEvent",
    "StepStartedEvent",
    "StepCompletedEvent",
    "ToolStartedEvent",
    "ToolCompletedEvent",
    "ToolFailedEvent",
    "InterruptRequestedEvent",
    "TokenDeltaEvent",
    "MessageCompleteEvent",
    # Cancellation
    "CancellationToken",
    "CancelledByToken",
    "cancellation_race",
    # Events
    "EventBus",
    "EventFilter",
    "InputReceived",
    "InputRequested",
    "ProgressUpdate",
    "SupervisionEvent",
    "WorkflowCancelled",
    "WorkflowCompleted",
    "WorkflowFailed",
    "WorkflowProgress",
    "WorkflowStarted",
    # HITL
    "ApprovalGate",
    "InputCancelledError",
    "InputManager",
    "InputRequest",
    "InputResponse",
    "InputStatus",
    "InputTimeoutError",
    # Runtime events
    "RuntimeEvent",
    "ExecutionStarted",
    "ExecutionCompleted",
    "ExecutionFailed",
    "StepStarted",
    "StepCompleted",
    "ToolCallStarted",
    "ToolCallCompleted",
    "ToolCallFailed",
    "InterruptRequested",
    "InterruptResolved",
    "InterruptTimedOut",
    "InterruptCancelled",
    "CancellationRequested",
    "ExecutionCancelled",
    "TokenDelta",
    "MessageComplete",
    # Supervise
    "supervise",
    "SupervisedRun",
]
