"""Cooperative cancellation propagation for supervision workflows."""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, Coroutine, TypeVar

from relaykit.exceptions import RelayKitError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CancelledByToken(RelayKitError):
    """Raised when work is cancelled via a CancellationToken."""

    def __init__(self, reason: str = "", partial_result: Any = None) -> None:
        self.reason = reason
        self.partial_result = partial_result
        msg = f"Cancelled: {reason}" if reason else "Cancelled"
        super().__init__(msg)


class CancellationToken:
    """Thread-safe and asyncio-safe cooperative cancellation token.

    Supports hierarchical cancellation: cancelling a parent automatically
    cancels all children. Callbacks (sync and async) are fired on cancellation.
    """

    def __init__(self, *, name: str = "", parent: CancellationToken | None = None) -> None:
        self._name = name
        self._parent = parent
        self._lock = threading.Lock()
        self._cancelled = False
        self._reason = ""
        self._partial_result: Any = None
        self._callbacks: list[Callable[[], Any]] = []
        self._children: list[CancellationToken] = []
        self._event: asyncio.Event | None = None
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._event_lock = threading.Lock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason

    @property
    def partial_result(self) -> Any:
        with self._lock:
            return self._partial_result

    def set_partial_result(self, value: Any) -> None:
        with self._lock:
            self._partial_result = value

    def _get_or_create_event(self) -> asyncio.Event:
        with self._event_lock:
            if self._event is None:
                self._event = asyncio.Event()
                self._event_loop = asyncio.get_running_loop()
                if self._cancelled:
                    self._event.set()
            return self._event

    def cancel(self, reason: str = "") -> None:
        callbacks_to_fire: list[Callable[[], Any]] = []
        children_to_cancel: list[CancellationToken] = []

        with self._lock:
            if self._cancelled:
                return
            self._cancelled = True
            self._reason = reason
            callbacks_to_fire = list(self._callbacks)
            children_to_cancel = list(self._children)

        with self._event_lock:
            if self._event is not None:
                loop = self._event_loop
                if loop is not None:
                    try:
                        if loop is asyncio.get_running_loop():
                            self._event.set()
                        else:
                            loop.call_soon_threadsafe(self._event.set)
                    except RuntimeError:
                        loop.call_soon_threadsafe(self._event.set)
                else:
                    self._event.set()

        for callback in callbacks_to_fire:
            try:
                result = callback()
                if inspect.isawaitable(result):
                    _schedule_awaitable(result)
            except Exception:
                logger.exception("Error in cancellation callback")

        for child in children_to_cancel:
            child.cancel(reason=reason)

    def on_cancel(self, callback: Callable[[], Any]) -> None:
        fire_now = False
        with self._lock:
            if self._cancelled:
                fire_now = True
            else:
                self._callbacks.append(callback)

        if fire_now:
            try:
                result = callback()
                if inspect.isawaitable(result):
                    _schedule_awaitable(result)
            except Exception:
                logger.exception("Error in cancellation callback")

    async def wait_for_cancellation(self) -> None:
        event = self._get_or_create_event()
        await event.wait()

    def child(self, name: str = "") -> CancellationToken:
        child_token = CancellationToken(name=name, parent=self)
        with self._lock:
            if self._cancelled:
                child_token.cancel(reason=self._reason)
            else:
                self._children.append(child_token)
        return child_token

    @asynccontextmanager
    async def scope(self, name: str = "") -> AsyncIterator[CancellationToken]:
        child_token = self.child(name=name)
        try:
            yield child_token
        finally:
            if not child_token.is_cancelled:
                child_token.cancel(reason="scope exited")

    def __repr__(self) -> str:
        state = "cancelled" if self.is_cancelled else "active"
        label = f" name={self._name!r}" if self._name else ""
        return f"<CancellationToken{label} {state}>"


async def cancellation_race(coro: Coroutine[Any, Any, T], token: CancellationToken) -> T:
    """Race a coroutine against a cancellation token.

    Returns the coroutine result if it completes first.
    Raises CancelledByToken if the token fires first.
    """
    task = asyncio.ensure_future(coro)
    cancel_wait = asyncio.ensure_future(token.wait_for_cancellation())

    try:
        done, pending = await asyncio.wait(
            {task, cancel_wait},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if task in done:
            cancel_wait.cancel()
            try:
                await cancel_wait
            except asyncio.CancelledError:
                pass
            return task.result()

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        raise CancelledByToken(
            reason=token.reason,
            partial_result=token.partial_result,
        )
    except BaseException:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if not cancel_wait.done():
            cancel_wait.cancel()
            try:
                await cancel_wait
            except asyncio.CancelledError:
                pass
        raise


def _schedule_awaitable(awaitable: Any) -> None:
    """Schedule an awaitable on the running event loop, if available."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(awaitable)
    except RuntimeError:
        logger.warning("Async cancellation callback registered but no running event loop")
