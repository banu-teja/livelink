from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from livelink.exceptions import RelayKitError

logger = logging.getLogger(__name__)


class InputTimeoutError(RelayKitError):
    def __init__(self, request_id: str, question: str, timeout: float) -> None:
        self.request_id = request_id
        self.question = question
        self.timeout = timeout
        super().__init__(f"Input request {request_id} timed out after {timeout}s: {question!r}")


class InputCancelledError(RelayKitError):
    def __init__(self, request_id: str, reason: str) -> None:
        self.request_id = request_id
        self.reason = reason
        super().__init__(f"Input request {request_id} cancelled: {reason}")


class InputStatus(Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    ANSWERED = "answered"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class InputRequest:
    question: str
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    options: list[str] | None = None
    input_type: Literal["text", "confirm", "choice", "free_form"] = "free_form"
    timeout: float | None = None
    context: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class InputResponse:
    request_id: str
    answer: str
    answered_at: float = field(default_factory=time.time)
    source: Literal["voice", "text", "ui", "timeout_default"] = "voice"


class _PendingRequest:
    __slots__ = ("request", "event", "response", "status", "cancel_reason")

    def __init__(self, request: InputRequest) -> None:
        self.request = request
        self.event = asyncio.Event()
        self.response: InputResponse | None = None
        self.status: InputStatus = InputStatus.PENDING
        self.cancel_reason: str = ""


class InputManager:
    def __init__(self, *, default_timeout: float = 60.0, event_bus: Any = None) -> None:
        self._default_timeout = default_timeout
        self._pending: dict[str, _PendingRequest] = {}
        self._event_bus: Any = event_bus

    async def request_input(
        self,
        question: str,
        *,
        options: list[str] | None = None,
        input_type: str = "free_form",
        timeout: float | None = None,
        context: dict[str, Any] | None = None,
        priority: int = 0,
    ) -> InputResponse:
        effective_timeout = timeout if timeout is not None else self._default_timeout

        request = InputRequest(
            question=question,
            options=options,
            input_type=input_type,  # type: ignore[arg-type]
            timeout=effective_timeout,
            context=context or {},
            priority=priority,
        )

        pending = _PendingRequest(request)
        self._pending[request.request_id] = pending

        logger.debug("Input requested: %s (id=%s)", question, request.request_id)
        self._emit_requested(request)

        try:
            await asyncio.wait_for(pending.event.wait(), timeout=effective_timeout)
        except asyncio.TimeoutError:
            pending.status = InputStatus.TIMED_OUT
            del self._pending[request.request_id]
            raise InputTimeoutError(request.request_id, question, effective_timeout)

        if pending.status == InputStatus.CANCELLED:
            raise InputCancelledError(request.request_id, pending.cancel_reason)

        assert pending.response is not None
        return pending.response

    def pending_requests(self) -> list[InputRequest]:
        return [p.request for p in self._pending.values() if p.status == InputStatus.PENDING]

    def resolve(self, request_id: str, answer: str, *, source: str = "voice") -> None:
        pending = self._pending.get(request_id)
        if pending is None:
            raise KeyError(f"No pending request with id {request_id}")

        if pending.status != InputStatus.PENDING:
            raise KeyError(f"Request {request_id} is not pending (status={pending.status.value})")

        pending.response = InputResponse(
            request_id=request_id,
            answer=answer,
            source=source,  # type: ignore[arg-type]
        )
        pending.status = InputStatus.ANSWERED
        pending.event.set()

        del self._pending[request_id]
        logger.debug("Input resolved: %s -> %r", request_id, answer)
        self._emit_received(request_id, answer)

    def cancel(self, request_id: str, reason: str = "cancelled") -> None:
        pending = self._pending.get(request_id)
        if pending is None:
            raise KeyError(f"No pending request with id {request_id}")

        pending.status = InputStatus.CANCELLED
        pending.cancel_reason = reason
        pending.event.set()

        del self._pending[request_id]
        logger.debug("Input cancelled: %s (%s)", request_id, reason)

    def cancel_all(self, reason: str = "session_closing") -> None:
        for request_id in list(self._pending.keys()):
            pending = self._pending[request_id]
            pending.status = InputStatus.CANCELLED
            pending.cancel_reason = reason
            pending.event.set()

        self._pending.clear()
        logger.debug("All input requests cancelled: %s", reason)

    def get_status(self, request_id: str) -> InputStatus:
        pending = self._pending.get(request_id)
        if pending is None:
            raise KeyError(f"No request with id {request_id}")
        return pending.status

    def next_pending(self) -> InputRequest | None:
        candidates = [p for p in self._pending.values() if p.status == InputStatus.PENDING]
        if not candidates:
            return None
        candidates.sort(key=lambda p: (-p.request.priority, p.request.created_at))
        return candidates[0].request

    def _emit_requested(self, request: InputRequest) -> None:
        if self._event_bus is None:
            return
        from livelink.supervision.events import InputRequested

        self._event_bus.emit_nowait(
            InputRequested(
                source="input_manager",
                request_id=request.request_id,
                workflow_id="",
                question=request.question,
                options=request.options,
                timeout=request.timeout,
            )
        )

    def _emit_received(self, request_id: str, answer: str) -> None:
        if self._event_bus is None:
            return
        from livelink.supervision.events import InputReceived

        self._event_bus.emit_nowait(
            InputReceived(
                source="input_manager",
                request_id=request_id,
                answer=answer,
            )
        )


class ApprovalGate:
    def __init__(self, input_manager: InputManager) -> None:
        self._manager = input_manager

    async def approve(
        self,
        action: str,
        *,
        context: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> bool:
        response = await self._manager.request_input(
            f"Should I proceed with: {action}?",
            options=["Yes", "No"],
            input_type="confirm",
            timeout=timeout,
            context=context,
        )
        return response.answer.lower() in ("yes", "y", "true", "1")
