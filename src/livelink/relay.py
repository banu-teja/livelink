from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable

from livelink.signals import (
    OperationalContextPolicy,
    OperationalSignal,
    RuntimeSignal,
)
from livelink.supervision import EventBus
from livelink.supervision.runtime_events import (
    ExecutionCancelled,
    ExecutionCompleted,
    ExecutionFailed,
    ExecutionStarted,
    InterruptRequested,
    InterruptResolved,
    InterruptTimedOut,
    RuntimeEvent,
    StepCompleted,
)

logger = logging.getLogger(__name__)

_URGENCY_LEVELS = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class SupervisionRelay:
    """Bridges supervised execution into conversational context.

    Subscribes to RuntimeEvents from a supervise() run,
    maps them to OperationalSignals via semantic compression,
    and injects them into the live session's context stream.
    """

    def __init__(
        self,
        policy: OperationalContextPolicy,
        event_bus: EventBus,
        inject: Callable[[OperationalSignal], Awaitable[None]],
    ) -> None:
        self._policy = policy
        self._event_bus = event_bus
        self._inject = inject
        self._run_id: str = ""
        self._subscription_id: str | None = None
        self._last_inject_time: float = 0.0

    async def start(self, run_id: str) -> None:
        """Begin relaying for a specific supervised run."""
        self._run_id = run_id
        self._subscription_id = self._event_bus.subscribe(
            RuntimeEvent,
            self._handle_event,  # type: ignore[arg-type]
        )

    async def stop(self) -> None:
        """Stop relaying, clean up subscriptions."""
        if self._subscription_id:
            self._event_bus.unsubscribe(self._subscription_id)
            self._subscription_id = None

    async def _handle_event(self, event: RuntimeEvent) -> None:
        """EventBus handler. Filters by run_id, maps, and injects."""
        if not hasattr(event, "run_id") or event.run_id != self._run_id:
            return

        signal = self._map_to_signal(event)
        if signal is None:
            return

        if not self._should_inject(signal):
            return

        self._last_inject_time = time.time()
        try:
            await self._inject(signal)
        except Exception:
            logger.warning("Failed to inject signal: %s", signal.signal.value, exc_info=True)

    def _map_to_signal(self, event: RuntimeEvent) -> OperationalSignal | None:
        """Semantic compression: RuntimeEvent -> OperationalSignal."""
        if isinstance(event, ExecutionStarted):
            return OperationalSignal(
                signal=RuntimeSignal.EXECUTION_STARTED,
                summary="Execution started",
                urgency="low",
                source_run_id=event.run_id,
            )
        if isinstance(event, ExecutionCompleted):
            return OperationalSignal(
                signal=RuntimeSignal.EXECUTION_COMPLETED,
                summary=f"Execution completed ({event.duration_ms:.0f}ms)",
                urgency="medium",
                source_run_id=event.run_id,
            )
        if isinstance(event, ExecutionFailed):
            return OperationalSignal(
                signal=RuntimeSignal.EXECUTION_FAILED,
                summary=f"Execution failed: {event.error}",
                urgency="high",
                source_run_id=event.run_id,
            )
        if isinstance(event, InterruptRequested):
            return OperationalSignal(
                signal=RuntimeSignal.APPROVAL_REQUIRED,
                summary=f"Approval required at step '{event.step_name}'",
                urgency="high",
                structured_data={
                    "interrupt_id": event.interrupt_id,
                    "payload": event.payload,
                },
                source_run_id=event.run_id,
            )
        if isinstance(event, InterruptResolved):
            return OperationalSignal(
                signal=RuntimeSignal.PROGRESS_MILESTONE,
                summary="Approval resolved, execution resuming",
                urgency="medium",
                source_run_id=event.run_id,
            )
        if isinstance(event, InterruptTimedOut):
            return OperationalSignal(
                signal=RuntimeSignal.TIMEOUT_APPROACHING,
                summary="Approval timed out",
                urgency="high",
                source_run_id=event.run_id,
            )
        if isinstance(event, StepCompleted):
            return OperationalSignal(
                signal=RuntimeSignal.PROGRESS_MILESTONE,
                summary=f"Step '{event.step_name}' completed",
                urgency="low",
                source_run_id=event.run_id,
            )
        if isinstance(event, ExecutionCancelled):
            return OperationalSignal(
                signal=RuntimeSignal.EXECUTION_FAILED,
                summary="Execution was cancelled",
                urgency="medium",
                source_run_id=event.run_id,
            )
        return None

    def _should_inject(self, signal: OperationalSignal) -> bool:
        """Policy enforcement: debounce, urgency filter, watch_signals."""
        policy = self._policy

        if policy.watch_signals and signal.signal not in policy.watch_signals:
            return False

        signal_level = _URGENCY_LEVELS.get(signal.urgency, 0)
        min_level = _URGENCY_LEVELS.get(policy.min_urgency, 0)
        if signal_level < min_level:
            return False

        if policy.debounce_ms > 0:
            elapsed_ms = (time.time() - self._last_inject_time) * 1000
            if elapsed_ms < policy.debounce_ms:
                return False

        return True
