"""Multi-agent handoffs: control transfer between agents.

A handoff is a tool that, when called by the LLM, signals the Runner to swap
the active agent. The new agent takes over the conversation completely.

This is distinct from agent.as_tool() which delegates a sub-task and returns
the result to the calling agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, TYPE_CHECKING

from relaykit.tools import Tool

if TYPE_CHECKING:
    from relaykit.agent import LiveAgent


@dataclass(frozen=True)
class Handoff:
    """Declares a handoff target for an agent.

    When the LLM calls the generated handoff tool, the Runner detects it
    and swaps the active agent to ``target``.

    Attributes:
        target: The agent to transfer control to.
        tool_name: Override the generated tool name (default: transfer_to_{name}).
        tool_description: Override the generated tool description.
        on_handoff: Optional async callback invoked during handoff (for logging, state transfer).
        input_filter: Optional transform applied to context before passing to new agent.
    """

    target: LiveAgent
    tool_name: str | None = None
    tool_description: str | None = None
    on_handoff: Callable[..., Any] | None = None
    input_filter: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def _agent_name(self) -> str:
        target_model = self.target.model
        parts = target_model.split("/")
        return parts[-1].replace("-", "_").replace(".", "_")

    def to_tool(self) -> Tool:
        """Generate the handoff tool that the LLM will call."""
        name = self.tool_name or f"transfer_to_{self._agent_name()}"
        description = self.tool_description or (
            f"Transfer the conversation to {self._agent_name()}. "
            f"Use this when the user's request is better handled by that agent."
        )

        async def _handoff_fn(reason: str = "") -> str:
            return f"__handoff__:{name}:{reason}"

        return Tool(
            name=name,
            description=description,
            parameters={
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Brief reason for the handoff.",
                    }
                },
            },
            fn=_handoff_fn,
            takes_context=False,
            requires_approval=False,
        )


HANDOFF_RESULT_PREFIX = "__handoff__:"


def is_handoff_result(result: str) -> bool:
    """Check if a tool result signals a handoff."""
    return result.startswith(HANDOFF_RESULT_PREFIX)


def parse_handoff_result(result: str) -> tuple[str, str]:
    """Extract (tool_name, reason) from a handoff result string."""
    parts = result[len(HANDOFF_RESULT_PREFIX) :].split(":", 1)
    tool_name = parts[0]
    reason = parts[1] if len(parts) > 1 else ""
    return tool_name, reason
