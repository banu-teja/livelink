from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TYPE_CHECKING

from relaykit.capabilities import Capability

if TYPE_CHECKING:
    from relaykit.adapters.base import BaseAdapter

_REGISTRY: dict[str, ModelInfo] = {}


@dataclass(frozen=True)
class ModelInfo:
    adapter_class: type[BaseAdapter]
    capabilities: frozenset[Capability]
    transport: Literal["websocket", "http"]
    default_config: dict[str, Any] | None = None
    provider: str | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None


def register_model(name: str, info: ModelInfo) -> None:
    _REGISTRY[name] = info


def resolve_model(name: str) -> ModelInfo:
    """Resolve a model name to its ModelInfo.

    Supports provider prefix routing: if ``name`` contains a ``/``, the lookup
    first tries an exact match on the full string, then falls back to matching
    the portion after the first ``/`` (the bare model name).

    Examples:
        resolve_model("gemini-3.1-flash-audio")  -> exact registry lookup
        resolve_model("gemini/gemini-3.1-flash-audio")
            -> tries "gemini/gemini-3.1-flash-audio",
               then "gemini-3.1-flash-audio"
    """
    if name in _REGISTRY:
        return _REGISTRY[name]

    if "/" in name:
        _provider, _, model_name = name.partition("/")
        if model_name in _REGISTRY:
            return _REGISTRY[model_name]

    available = ", ".join(sorted(_REGISTRY.keys())) or "(none registered)"
    hint = (
        "Install a provider: pip install relaykit[gemini] or relaykit[openai]"
        if not _REGISTRY
        else "Register custom models with register_model()"
    )
    raise ValueError(f"Unknown model: {name!r}. Available: {available}. {hint}")


def list_models() -> dict[str, ModelInfo]:
    return dict(_REGISTRY)
