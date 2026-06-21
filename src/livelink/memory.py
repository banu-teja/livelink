from __future__ import annotations

from collections import deque

from livelink.signals import OperationalSignal


class OperationalMemory:
    """Delegation-scoped runtime memory.

    Lifetime: session-scoped, delegation-scoped, reconnect-resilient,
    bounded, ephemeral, non-persistent.
    """

    def __init__(self, max_signals: int = 20) -> None:
        self._signals: deque[OperationalSignal] = deque(maxlen=max_signals)
        self._pending_interrupt: OperationalSignal | None = None

    @property
    def pending_interrupt(self) -> OperationalSignal | None:
        return self._pending_interrupt

    def record(self, signal: OperationalSignal) -> None:
        """Record a signal for potential replay on reconnect."""
        self._signals.append(signal)

    def set_pending_interrupt(self, signal: OperationalSignal) -> None:
        """Mark an interrupt as pending resolution."""
        self._pending_interrupt = signal

    def clear_pending_interrupt(self) -> None:
        """Clear the pending interrupt after resolution."""
        self._pending_interrupt = None

    def restore_context(self, max_restore: int = 5) -> list[OperationalSignal]:
        """Return signals needed to restore model awareness on reconnect."""
        result: list[OperationalSignal] = []
        recent = list(self._signals)[-max_restore:]
        result.extend(recent)
        if self._pending_interrupt and self._pending_interrupt not in result:
            result.append(self._pending_interrupt)
        return result

    def summarize(self) -> str:
        """One-line operational summary."""
        if not self._signals:
            return ""
        return self._signals[-1].summary


class OperationalContextWindow:
    """Bounded sliding window of active operational signals.

    What the model currently knows about ongoing execution.
    Reconnect-resilient within session lifetime.
    """

    def __init__(self, max_size: int = 5) -> None:
        self._signals: deque[OperationalSignal] = deque(maxlen=max_size)

    def push(self, signal: OperationalSignal) -> OperationalSignal | None:
        """Add signal, return evicted signal if at capacity."""
        evicted = None
        if len(self._signals) == self._signals.maxlen:
            evicted = self._signals[0]
        self._signals.append(signal)
        return evicted

    def render(self) -> str:
        """Produce current operational context for injection."""
        if not self._signals:
            return ""
        lines = [f"- {s.summary} ({s.urgency})" for s in self._signals]
        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all signals."""
        self._signals.clear()
