"""Generic execution supervisor: consumes ExecutionAdapter, emits RuntimeEvents.

Orchestrates the lifecycle of a supervised execution run, handling interrupt/resume
via InputManager and cooperative cancellation via CancellationToken.
"""

from __future__ import annotations

import inspect
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Literal

from relaykit.supervision.adapter import (
    AdapterEvent,
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
from relaykit.supervision.cancellation import CancellationToken
from relaykit.supervision.events import EventBus
from relaykit.supervision.hitl import InputManager, InputTimeoutError
from relaykit.supervision.runtime_events import (
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

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _resolve_stream(result: Any) -> AsyncIterator[AdapterEvent]:
    """Resolve adapter method return to an AsyncIterator.

    Handles both async generator functions (return iterator directly)
    and coroutine functions (return awaitable that resolves to iterator).
    """
    if inspect.isasyncgen(result):
        return result
    return await result


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SupervisedRun:
    output: Any = None
    interrupts_handled: int = 0
    stopped_reason: Literal["completed", "cancelled", "failed"] = "completed"
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# Typed stream results (NO string sentinels)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _StreamCompleted:
    pass


@dataclass(frozen=True)
class _StreamInterrupted:
    event: InterruptRequestedEvent


@dataclass(frozen=True)
class _StreamFailed:
    error: Exception


@dataclass(frozen=True)
class _StreamCancelled:
    pass


@dataclass(frozen=True)
class _StreamExhausted:
    pass


_StreamResult = (
    _StreamCompleted | _StreamInterrupted | _StreamFailed | _StreamCancelled | _StreamExhausted
)


# ---------------------------------------------------------------------------
# Pure event mapping
# ---------------------------------------------------------------------------


def _map_event(event: AdapterEvent, source: str, run_id: str) -> RuntimeEvent | None:
    """Map an AdapterEvent to a RuntimeEvent. Returns None for events handled separately."""
    if isinstance(event, LifecycleStartedEvent):
        return ExecutionStarted(source=source, run_id=run_id, input_summary=event.input_summary)
    if isinstance(event, LifecycleCompletedEvent):
        return ExecutionCompleted(
            source=source,
            run_id=run_id,
            output_summary=event.output_summary,
            duration_ms=event.duration_ms,
        )
    if isinstance(event, StepStartedEvent):
        return StepStarted(
            source=source,
            run_id=run_id,
            step_name=event.step_name,
            step_index=event.step_index,
        )
    if isinstance(event, StepCompletedEvent):
        return StepCompleted(
            source=source,
            run_id=run_id,
            step_name=event.step_name,
            step_index=event.step_index,
            duration_ms=event.duration_ms,
        )
    if isinstance(event, ToolStartedEvent):
        return ToolCallStarted(
            source=source,
            run_id=run_id,
            tool_name=event.tool_name,
            call_id=event.call_id,
            arguments_summary=event.arguments_summary,
        )
    if isinstance(event, ToolCompletedEvent):
        return ToolCallCompleted(
            source=source,
            run_id=run_id,
            tool_name=event.tool_name,
            call_id=event.call_id,
            result_summary=event.result_summary,
            duration_ms=event.duration_ms,
        )
    if isinstance(event, ToolFailedEvent):
        return ToolCallFailed(
            source=source,
            run_id=run_id,
            tool_name=event.tool_name,
            call_id=event.call_id,
            error=event.error,
        )
    if isinstance(event, MessageCompleteEvent):
        return MessageComplete(
            source=source,
            run_id=run_id,
            role=event.role,
            content=event.content,
            step_name=event.step_name,
        )
    # TokenDeltaEvent and InterruptRequestedEvent handled separately
    # LifecycleFailedEvent handled in _consume_stream directly
    return None


# ---------------------------------------------------------------------------
# Stream consumer
# ---------------------------------------------------------------------------


async def _consume_stream(
    stream: AsyncIterator[AdapterEvent],
    *,
    emit: Callable[[RuntimeEvent], None],
    cancelled: Callable[[], bool],
    source: str,
    run_id: str,
    token_coalesce_ms: float,
) -> _StreamResult:
    """Consume the adapter event stream, emitting RuntimeEvents.

    Returns a typed result indicating how the stream ended.
    """
    token_buffer: list[str] = []
    token_step: str = ""
    last_flush_time: float = time.monotonic()
    coalesce_interval_s = token_coalesce_ms / 1000.0

    def _flush_tokens() -> None:
        nonlocal token_buffer, last_flush_time
        if token_buffer:
            content = "".join(token_buffer)
            emit(TokenDelta(source=source, run_id=run_id, content=content, step_name=token_step))
            token_buffer = []
            last_flush_time = time.monotonic()

    try:
        async for event in stream:
            if cancelled():
                _flush_tokens()
                return _StreamCancelled()

            if isinstance(event, InterruptRequestedEvent):
                _flush_tokens()
                return _StreamInterrupted(event=event)

            if isinstance(event, LifecycleCompletedEvent):
                _flush_tokens()
                mapped = _map_event(event, source, run_id)
                if mapped is not None:
                    emit(mapped)
                return _StreamCompleted()

            if isinstance(event, LifecycleFailedEvent):
                _flush_tokens()
                return _StreamFailed(error=RuntimeError(event.error))

            if isinstance(event, TokenDeltaEvent):
                token_buffer.append(event.content)
                token_step = event.step_name
                now = time.monotonic()
                if (now - last_flush_time) >= coalesce_interval_s:
                    _flush_tokens()
                continue

            mapped = _map_event(event, source, run_id)
            if mapped is not None:
                emit(mapped)

    except Exception as exc:
        _flush_tokens()
        return _StreamFailed(error=exc)

    _flush_tokens()
    return _StreamExhausted()


# ---------------------------------------------------------------------------
# Public supervise() function
# ---------------------------------------------------------------------------


async def supervise(
    adapter: Any,
    input: Any,
    *,
    event_bus: EventBus | None = None,
    input_manager: InputManager | None = None,
    cancellation_token: CancellationToken | None = None,
    interrupt_timeout: float | None = None,
    token_coalesce_ms: float = 50.0,
    run_id: str | None = None,
) -> SupervisedRun:
    """Supervise execution of an adapter, emitting RuntimeEvents and handling interrupts."""
    run_id = run_id or uuid.uuid4().hex
    bus = event_bus if event_bus is not None else EventBus()
    source = getattr(adapter, "SOURCE", "unknown_adapter")
    start_time = time.monotonic()
    interrupts_handled = 0

    def emit(event: RuntimeEvent) -> None:
        bus.emit_nowait(event)

    def is_cancelled() -> bool:
        if cancellation_token is None:
            return False
        return cancellation_token.is_cancelled

    try:
        stream = await _resolve_stream(adapter.start(input))
        # Use the same stream variable for the consume loop; after resume, reassign
        while True:
            result = await _consume_stream(
                stream,
                emit=emit,
                cancelled=is_cancelled,
                source=source,
                run_id=run_id,
                token_coalesce_ms=token_coalesce_ms,
            )

            if isinstance(result, _StreamCompleted):
                duration = (time.monotonic() - start_time) * 1000.0
                return SupervisedRun(
                    stopped_reason="completed",
                    interrupts_handled=interrupts_handled,
                    duration_ms=duration,
                )

            if isinstance(result, _StreamExhausted):
                duration = (time.monotonic() - start_time) * 1000.0
                return SupervisedRun(
                    stopped_reason="completed",
                    interrupts_handled=interrupts_handled,
                    duration_ms=duration,
                )

            if isinstance(result, _StreamFailed):
                emit(
                    ExecutionFailed(
                        source=source,
                        run_id=run_id,
                        error=str(result.error),
                    )
                )
                duration = (time.monotonic() - start_time) * 1000.0
                return SupervisedRun(
                    stopped_reason="failed",
                    interrupts_handled=interrupts_handled,
                    duration_ms=duration,
                )

            if isinstance(result, _StreamCancelled):
                await adapter.cancel()
                emit(ExecutionCancelled(source=source, run_id=run_id))
                duration = (time.monotonic() - start_time) * 1000.0
                return SupervisedRun(
                    stopped_reason="cancelled",
                    interrupts_handled=interrupts_handled,
                    duration_ms=duration,
                )

            if isinstance(result, _StreamInterrupted):
                interrupt_event = result.event
                emit(
                    InterruptRequested(
                        source=source,
                        run_id=run_id,
                        interrupt_id=interrupt_event.interrupt_id,
                        payload=interrupt_event.payload,
                        step_name=interrupt_event.step_name,
                    )
                )

                if input_manager is None:
                    emit(
                        ExecutionFailed(
                            source=source,
                            run_id=run_id,
                            error="Interrupt received but no InputManager configured",
                        )
                    )
                    await adapter.cancel()
                    duration = (time.monotonic() - start_time) * 1000.0
                    return SupervisedRun(
                        stopped_reason="failed",
                        interrupts_handled=interrupts_handled,
                        duration_ms=duration,
                    )

                # Wait for human input
                try:
                    wait_start = time.monotonic()
                    response = await input_manager.request_input(
                        str(interrupt_event.payload),
                        timeout=interrupt_timeout,
                        context={
                            "interrupt_id": interrupt_event.interrupt_id,
                            "step_name": interrupt_event.step_name,
                        },
                    )
                    wait_duration_ms = (time.monotonic() - wait_start) * 1000.0

                    emit(
                        InterruptResolved(
                            source=source,
                            run_id=run_id,
                            interrupt_id=interrupt_event.interrupt_id,
                            resolution=response.answer,
                            wait_duration_ms=wait_duration_ms,
                        )
                    )

                    interrupts_handled += 1
                    stream = await _resolve_stream(adapter.resume(response.answer))

                except InputTimeoutError:
                    emit(
                        InterruptTimedOut(
                            source=source,
                            run_id=run_id,
                            interrupt_id=interrupt_event.interrupt_id,
                            timeout_ms=(interrupt_timeout or 0.0) * 1000.0,
                        )
                    )
                    await adapter.cancel()
                    duration = (time.monotonic() - start_time) * 1000.0
                    return SupervisedRun(
                        stopped_reason="failed",
                        interrupts_handled=interrupts_handled,
                        duration_ms=duration,
                    )

                except Exception as exc:
                    if is_cancelled():
                        emit(
                            InterruptCancelled(
                                source=source,
                                run_id=run_id,
                                interrupt_id=interrupt_event.interrupt_id,
                                reason="cancelled_during_wait",
                            )
                        )
                        await adapter.cancel()
                        duration = (time.monotonic() - start_time) * 1000.0
                        return SupervisedRun(
                            stopped_reason="cancelled",
                            interrupts_handled=interrupts_handled,
                            duration_ms=duration,
                        )
                    emit(
                        ExecutionFailed(
                            source=source,
                            run_id=run_id,
                            error=f"Interrupt handling failed: {exc}",
                        )
                    )
                    await adapter.cancel()
                    duration = (time.monotonic() - start_time) * 1000.0
                    return SupervisedRun(
                        stopped_reason="failed",
                        interrupts_handled=interrupts_handled,
                        duration_ms=duration,
                    )

    except Exception as exc:
        emit(ExecutionFailed(source=source, run_id=run_id, error=str(exc)))
        duration = (time.monotonic() - start_time) * 1000.0
        return SupervisedRun(
            stopped_reason="failed",
            interrupts_handled=interrupts_handled,
            duration_ms=duration,
        )
