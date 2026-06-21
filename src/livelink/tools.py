"""Tool system: registration, schema inference, context injection, execution.

Two registration patterns:
1. Standalone: ``@tool`` decorator creates reusable Tool objects
2. Bound: ``@agent.tool`` registers directly on an agent instance

Tools receive an optional ``ToolContext`` as first argument for dependency injection.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, get_args, get_origin

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    """Injected context available to tool functions.

    If a tool's first parameter is annotated as ``ToolContext``, the runtime
    injects it automatically — it is NOT sent to the LLM as a parameter.

    Attributes:
        deps: User-provided dependencies (passed via ``agent.session(deps=...)``)
        session_state: Mutable per-session key-value state
        history: Conversation turns so far (read-only snapshot)
    """

    deps: Any = None
    session_state: dict[str, Any] = field(default_factory=dict)
    history: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class Tool:
    """A registered tool definition with schema and callable.

    Create via the ``@tool`` decorator or ``Tool.from_function()``.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., Any]
    takes_context: bool = False
    requires_approval: bool = False

    @classmethod
    def from_function(
        cls,
        fn: Callable[..., Any],
        *,
        name: str | None = None,
        requires_approval: bool = False,
    ) -> Tool:
        """Create a Tool from a function, inferring schema from signature + docstring."""
        tool_name = name or fn.__name__
        description, param_descriptions = _parse_docstring(fn)
        parameters, takes_ctx = _infer_parameters(fn, param_descriptions)
        return cls(
            name=tool_name,
            description=description,
            parameters=parameters,
            fn=fn,
            takes_context=takes_ctx,
            requires_approval=requires_approval,
        )


def tool(
    fn: Callable[..., Any] | None = None,
    *,
    requires_approval: bool = False,
) -> Tool | Callable[[Callable[..., Any]], Tool]:
    """Standalone decorator to create a reusable Tool from a function.

    Can be used bare or with parameters::

        @tool
        async def get_weather(city: str) -> str:
            \"\"\"Get current weather.\"\"\"
            return "sunny"

        @tool(requires_approval=True)
        async def delete_account(user_id: str) -> str:
            \"\"\"Delete a user account. Requires human approval.\"\"\"
            ...
    """
    if fn is not None:
        return Tool.from_function(fn, requires_approval=requires_approval)

    def _decorator(f: Callable[..., Any]) -> Tool:
        return Tool.from_function(f, requires_approval=requires_approval)

    return _decorator


class ToolRegistry:
    """Collection of tools with schema generation and concurrent execution."""

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for t in tools or []:
            self._tools[t.name] = t

    def register_function(
        self,
        fn: Callable[..., Any],
        *,
        name: str | None = None,
        requires_approval: bool = False,
    ) -> Tool:
        """Register a function as a tool (used by @agent.tool decorator)."""
        t = Tool.from_function(fn, name=name, requires_approval=requires_approval)
        self._tools[t.name] = t
        return t

    def add(self, t: Tool) -> None:
        """Add a pre-built Tool object."""
        self._tools[t.name] = t

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    @property
    def declarations(self) -> list[dict[str, Any]]:
        """JSON-serializable tool declarations for provider APIs."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in self._tools.values()
        ]

    async def execute(
        self,
        calls: list[ToolCall],
        *,
        context: ToolContext | None = None,
        max_concurrency: int = 10,
    ) -> list[ToolResult]:
        """Execute tool calls concurrently and return results."""
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _run_one(call: ToolCall) -> ToolResult:
            async with semaphore:
                return await self._execute_one(call, context)

        results = await asyncio.gather(*[_run_one(c) for c in calls])
        return list(results)

    async def _execute_one(self, call: ToolCall, context: ToolContext | None) -> ToolResult:
        """Execute a single tool call with error handling."""
        t = self._tools.get(call.name)
        if t is None:
            return ToolResult(
                call_id=call.id,
                output=json.dumps({"error": f"Unknown tool: {call.name}"}),
                is_error=True,
            )

        try:
            if t.takes_context:
                result = t.fn(context or ToolContext(), **call.arguments)
            else:
                result = t.fn(**call.arguments)

            if inspect.isawaitable(result):
                result = await result

            output = json.dumps(result) if not isinstance(result, str) else result
        except Exception as exc:
            logger.warning("Tool %s raised: %s", call.name, exc)
            output = json.dumps({"error": str(exc)})
            return ToolResult(call_id=call.id, output=output, is_error=True)

        return ToolResult(call_id=call.id, output=output, is_error=False)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __iter__(self):
        return iter(self._tools.values())

    def __bool__(self) -> bool:
        return len(self._tools) > 0


@dataclass(frozen=True)
class ToolCall:
    """A tool call request from the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """Result of executing a tool call."""

    call_id: str
    output: str
    is_error: bool = False


# --- Schema inference ---


def _parse_docstring(fn: Callable[..., Any]) -> tuple[str, dict[str, str]]:
    """Parse function docstring for description and parameter descriptions.

    Supports Google-style Args: sections::

        def my_func(city: str, units: str = "celsius"):
            \"\"\"Get weather for a location.

            Args:
                city: The city name to look up
                units: Temperature units (celsius or fahrenheit)
            \"\"\"
    """
    doc = inspect.getdoc(fn) or ""
    if not doc:
        return fn.__name__, {}

    lines = doc.strip().split("\n")
    description_lines: list[str] = []
    param_descriptions: dict[str, str] = {}
    in_args_section = False
    current_param: str | None = None

    for line in lines:
        stripped = line.strip()

        if stripped.lower() in ("args:", "arguments:", "parameters:", "params:"):
            in_args_section = True
            continue

        if in_args_section:
            if stripped.lower() in (
                "returns:",
                "raises:",
                "examples:",
                "example:",
                "note:",
                "notes:",
            ):
                break

            if not stripped:
                continue

            param_match = re.match(r"^\s*(\w+)\s*(?:\([^)]*\))?\s*:\s*(.+)", line)
            if param_match:
                current_param = param_match.group(1)
                param_descriptions[current_param] = param_match.group(2).strip()
            elif current_param and stripped:
                param_descriptions[current_param] += " " + stripped
        else:
            if stripped:
                description_lines.append(stripped)
            # Don't break on blank lines — Args: section may follow

    description = " ".join(description_lines) if description_lines else fn.__name__
    return description, param_descriptions


def _infer_parameters(
    fn: Callable[..., Any],
    param_descriptions: dict[str, str],
) -> tuple[dict[str, Any], bool]:
    """Infer JSON Schema from function signature. Returns (schema, takes_context)."""
    sig = inspect.signature(fn)
    try:
        hints = inspect.get_annotations(fn, eval_str=True)
    except Exception:
        hints = {}

    properties: dict[str, Any] = {}
    required: list[str] = []
    takes_context = False

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue

        hint = hints.get(param_name)
        if hint is ToolContext or (isinstance(hint, str) and hint == "ToolContext"):
            takes_context = True
            continue

        prop = _type_to_schema(hint)
        if param_name in param_descriptions:
            prop["description"] = param_descriptions[param_name]

        properties[param_name] = prop
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema, takes_context


def _type_to_schema(hint: Any) -> dict[str, Any]:
    """Convert a Python type hint to JSON Schema."""
    if hint is None or hint is inspect.Parameter.empty:
        return {"type": "string"}

    origin = get_origin(hint)
    args = get_args(hint)

    if hint is str:
        return {"type": "string"}
    elif hint is int:
        return {"type": "integer"}
    elif hint is float:
        return {"type": "number"}
    elif hint is bool:
        return {"type": "boolean"}
    elif origin is list or hint is list:
        item_schema = _type_to_schema(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": item_schema}
    elif origin is dict or hint is dict:
        return {"type": "object"}
    elif hasattr(hint, "__members__"):
        return {"type": "string", "enum": list(hint.__members__.keys())}

    return {"type": "string"}
