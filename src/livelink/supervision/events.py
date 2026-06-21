"""EventBus: typed pub/sub for supervision observability.

Provides multi-subscriber, type-based event dispatch for external orchestrators
to monitor session activity without owning execution.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="SupervisionEvent")


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SupervisionEvent:
    source: str
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class WorkflowStarted(SupervisionEvent):
    workflow_id: str = ""
    name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowProgress(SupervisionEvent):
    workflow_id: str = ""
    step: str = ""
    progress: float = 0.0
    message: str = ""
    data: dict[str, Any] | None = None


@dataclass(frozen=True)
class WorkflowCompleted(SupervisionEvent):
    workflow_id: str = ""
    result: Any = None
    duration_ms: float = 0.0


@dataclass(frozen=True)
class WorkflowFailed(SupervisionEvent):
    workflow_id: str = ""
    error: str = ""
    partial_result: Any | None = None


@dataclass(frozen=True)
class WorkflowCancelled(SupervisionEvent):
    workflow_id: str = ""
    reason: str = ""


@dataclass(frozen=True)
class InputRequested(SupervisionEvent):
    request_id: str = ""
    workflow_id: str = ""
    question: str = ""
    options: list[str] | None = None
    timeout: float | None = None


@dataclass(frozen=True)
class InputReceived(SupervisionEvent):
    request_id: str = ""
    answer: str = ""


@dataclass(frozen=True)
class ProgressUpdate(SupervisionEvent):
    workflow_id: str = ""
    message: str = ""
    progress: float = 0.0
    structured_data: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Session lifecycle events (emitted by supervised RealtimeSession)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionStarted(SupervisionEvent):
    model: str = ""
    session_id: str = ""


@dataclass(frozen=True)
class SessionEnded(SupervisionEvent):
    session_id: str = ""
    reason: str = ""


@dataclass(frozen=True)
class TurnStarted(SupervisionEvent):
    role: str = ""


@dataclass(frozen=True)
class TurnEnded(SupervisionEvent):
    role: str = ""


@dataclass(frozen=True)
class ToolExecutionStarted(SupervisionEvent):
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""


@dataclass(frozen=True)
class ToolExecutionCompleted(SupervisionEvent):
    tool_name: str = ""
    call_id: str = ""
    result: str = ""
    duration_ms: float = 0.0


@dataclass(frozen=True)
class ToolExecutionFailed(SupervisionEvent):
    tool_name: str = ""
    call_id: str = ""
    error: str = ""


@dataclass(frozen=True)
class ToolApprovalRequested(SupervisionEvent):
    tool_name: str = ""
    call_id: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolApprovalResolved(SupervisionEvent):
    tool_name: str = ""
    call_id: str = ""
    approved: bool = False


# ---------------------------------------------------------------------------
# EventFilter protocol
# ---------------------------------------------------------------------------


class EventFilter(Protocol):
    def should_dispatch(self, event: SupervisionEvent) -> bool: ...


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


_Handler = Callable[[Any], Awaitable[None] | None]


@dataclass
class _Subscription:
    id: str
    event_type: type[SupervisionEvent] | None
    handler: _Handler
    filter: EventFilter | None


class EventBus:
    def __init__(self, *, history_limit: int = 1000) -> None:
        self._subscriptions: dict[str, _Subscription] = {}
        self._history: deque[SupervisionEvent] = deque(maxlen=history_limit)
        self._waiters: list[tuple[type[SupervisionEvent], asyncio.Future[SupervisionEvent]]] = []
        self._lock = asyncio.Lock()

    def subscribe(
        self,
        event_type: type[T],
        handler: Callable[[T], Awaitable[None] | None],
        *,
        filter: EventFilter | None = None,
    ) -> str:
        sub_id = uuid.uuid4().hex
        self._subscriptions[sub_id] = _Subscription(
            id=sub_id,
            event_type=event_type,
            handler=handler,
            filter=filter,
        )
        return sub_id

    def subscribe_all(
        self,
        handler: Callable[[SupervisionEvent], Awaitable[None] | None],
        *,
        filter: EventFilter | None = None,
    ) -> str:
        sub_id = uuid.uuid4().hex
        self._subscriptions[sub_id] = _Subscription(
            id=sub_id,
            event_type=None,
            handler=handler,
            filter=filter,
        )
        return sub_id

    def unsubscribe(self, subscription_id: str) -> None:
        self._subscriptions.pop(subscription_id, None)

    async def emit(self, event: SupervisionEvent) -> None:
        self._history.append(event)
        self._resolve_waiters(event)

        if not self._subscriptions:
            return

        tasks: list[asyncio.Task[None]] = []
        for sub in list(self._subscriptions.values()):
            if not self._matches(sub, event):
                continue
            try:
                result = sub.handler(event)
                if asyncio.iscoroutine(result):
                    tasks.append(asyncio.ensure_future(result))
            except Exception:
                logger.exception("EventBus handler %s raised", sub.id)

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.exception("EventBus async handler raised: %s", r)

    def emit_nowait(self, event: SupervisionEvent) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.emit(event))
        except RuntimeError:
            logger.warning("emit_nowait called outside running event loop — event dropped")

    def history(
        self, event_type: type[SupervisionEvent] | None = None, *, limit: int = 100
    ) -> list[SupervisionEvent]:
        if event_type is None:
            items = list(self._history)
        else:
            items = [e for e in self._history if isinstance(e, event_type)]
        return items[-limit:]

    def clear_history(self) -> None:
        self._history.clear()

    async def wait_for(self, event_type: type[T], *, timeout: float | None = None) -> T:
        future: asyncio.Future[SupervisionEvent] = asyncio.get_running_loop().create_future()
        waiter = (event_type, future)
        self._waiters.append(waiter)
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result  # type: ignore[return-value]
        except asyncio.TimeoutError:
            raise TimeoutError(f"Timed out waiting for {event_type.__name__}") from None
        finally:
            if waiter in self._waiters:
                self._waiters.remove(waiter)

    def _resolve_waiters(self, event: SupervisionEvent) -> None:
        resolved: list[tuple[type[SupervisionEvent], asyncio.Future[SupervisionEvent]]] = []
        for waiter in self._waiters:
            event_type, future = waiter
            if isinstance(event, event_type) and not future.done():
                future.set_result(event)
                resolved.append(waiter)
        for w in resolved:
            self._waiters.remove(w)

    def _matches(self, sub: _Subscription, event: SupervisionEvent) -> bool:
        if sub.event_type is not None and not isinstance(event, sub.event_type):
            return False
        if sub.filter is not None and not sub.filter.should_dispatch(event):
            return False
        return True
