"""Guardrails: input and output validation for agent conversations.

Guardrails inspect messages at system boundaries and can block, modify,
or flag content before it reaches the model (input) or the user (output).
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GuardrailResult:
    """Result of a guardrail check.

    Attributes:
        action: What to do with the message.
            - "pass": Allow through unchanged.
            - "block": Reject the message entirely.
            - "modify": Allow through with modifications (use ``modified_content``).
        message: Human-readable explanation (for logging/debugging).
        modified_content: Replacement content when action is "modify".
        metadata: Optional structured data for observability.
    """

    action: Literal["pass", "block", "modify"] = "pass"
    message: str = ""
    modified_content: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.action in ("pass", "modify")

    @property
    def blocked(self) -> bool:
        return self.action == "block"


@dataclass(frozen=True)
class Guardrail:
    """A registered guardrail with its handler function.

    Attributes:
        name: Guardrail identifier.
        fn: The guardrail function (sync or async, returns GuardrailResult).
        kind: Whether this runs on input or output.
    """

    name: str
    fn: Callable[..., Any]
    kind: Literal["input", "output"]

    async def run(self, content: str, **kwargs: Any) -> GuardrailResult:
        """Execute the guardrail function."""
        try:
            result = self.fn(content, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, GuardrailResult):
                return result
            if isinstance(result, bool):
                return GuardrailResult(
                    action="pass" if result else "block",
                    message="" if result else f"Blocked by {self.name}",
                )
            return GuardrailResult(action="pass")
        except Exception as exc:
            logger.warning("Guardrail %s raised: %s", self.name, exc)
            return GuardrailResult(
                action="pass",
                message=f"Guardrail error (failing open): {exc}",
            )


def input_guardrail(
    fn: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
) -> Any:
    """Decorator to register an input guardrail.

    The decorated function receives the user's message content as its first
    argument and should return a GuardrailResult (or bool for simple cases).

    Usage::

        @input_guardrail
        async def block_profanity(content: str) -> GuardrailResult:
            if has_profanity(content):
                return GuardrailResult(action="block", message="Profanity detected")
            return GuardrailResult(action="pass")

        @input_guardrail(name="length_check")
        def check_length(content: str) -> bool:
            return len(content) < 10000
    """
    if fn is not None:
        guardrail_name = name or fn.__name__
        return Guardrail(name=guardrail_name, fn=fn, kind="input")

    def _decorator(f: Callable[..., Any]) -> Guardrail:
        guardrail_name = name or f.__name__
        return Guardrail(name=guardrail_name, fn=f, kind="input")

    return _decorator


def output_guardrail(
    fn: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
) -> Any:
    """Decorator to register an output guardrail.

    The decorated function receives the model's response content as its first
    argument and should return a GuardrailResult (or bool for simple cases).

    Usage::

        @output_guardrail
        async def redact_pii(content: str) -> GuardrailResult:
            cleaned = remove_pii(content)
            if cleaned != content:
                return GuardrailResult(action="modify", modified_content=cleaned)
            return GuardrailResult(action="pass")
    """
    if fn is not None:
        guardrail_name = name or fn.__name__
        return Guardrail(name=guardrail_name, fn=fn, kind="output")

    def _decorator(f: Callable[..., Any]) -> Guardrail:
        guardrail_name = name or f.__name__
        return Guardrail(name=guardrail_name, fn=f, kind="output")

    return _decorator


async def run_guardrails(
    guardrails: list[Guardrail],
    content: str,
    **kwargs: Any,
) -> GuardrailResult:
    """Run a list of guardrails sequentially, short-circuiting on block.

    Returns the first blocking result, the last modify result, or pass.
    """
    final_content = content
    last_modify: GuardrailResult | None = None

    for g in guardrails:
        result = await g.run(final_content, **kwargs)
        if result.blocked:
            return result
        if result.action == "modify" and result.modified_content is not None:
            final_content = result.modified_content
            last_modify = result

    if last_modify is not None:
        return GuardrailResult(
            action="modify",
            modified_content=final_content,
            message=last_modify.message,
        )
    return GuardrailResult(action="pass")
