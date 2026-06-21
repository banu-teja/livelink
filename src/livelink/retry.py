"""Retry logic with configurable exponential backoff."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from livelink.exceptions import (
    AdapterError,
    AuthenticationError,
    ConnectionError,
    RateLimitError,
    UnsupportedModalityError,
)

T = TypeVar("T")

# Default exceptions that trigger retry
RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    AdapterError,
    ConnectionError,
    RateLimitError,
)

# Exceptions that should never be retried
NON_RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    AuthenticationError,
    UnsupportedModalityError,
)


@dataclass(frozen=True)
class RetryPolicy:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple[type[Exception], ...] = RETRYABLE_EXCEPTIONS

    def delay_for_attempt(self, attempt: int) -> float:
        """Calculate delay for a given attempt number (0-indexed)."""
        delay = self.base_delay * (self.exponential_base**attempt)
        delay = min(delay, self.max_delay)
        if self.jitter:
            delay = delay * (0.5 + random.random())
        return delay


# Singleton default policy
DEFAULT_RETRY_POLICY = RetryPolicy()
NO_RETRY_POLICY = RetryPolicy(max_retries=0)


def retry_sync(
    fn: Callable[..., T],
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    *args: Any,
    **kwargs: Any,
) -> T:
    """Execute a sync function with retry logic."""
    last_exception: Exception | None = None

    for attempt in range(policy.max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except NON_RETRYABLE_EXCEPTIONS:
            raise
        except policy.retryable_exceptions as exc:
            last_exception = exc
            if attempt < policy.max_retries:
                delay = policy.delay_for_attempt(attempt)
                time.sleep(delay)
            else:
                raise
        except Exception:
            raise

    raise last_exception  # type: ignore[misc]  # unreachable but satisfies mypy


async def retry_async(
    fn: Callable[..., Any],
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Execute an async function with retry logic."""
    last_exception: Exception | None = None

    for attempt in range(policy.max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except NON_RETRYABLE_EXCEPTIONS:
            raise
        except policy.retryable_exceptions as exc:
            last_exception = exc
            if attempt < policy.max_retries:
                delay = policy.delay_for_attempt(attempt)
                await asyncio.sleep(delay)
            else:
                raise
        except Exception:
            raise

    raise last_exception  # type: ignore[misc]
