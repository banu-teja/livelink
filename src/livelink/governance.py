from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from livelink.signals import RuntimeSignal


class ResolutionAuthority(Enum):
    """Who is allowed to resolve a given interrupt."""

    CONVERSATIONAL = "conversational"
    SUPERVISOR = "supervisor"
    EITHER = "either"
    ESCALATING = "escalating"


@dataclass(frozen=True)
class GovernanceRule:
    """Resolution authority for a signal type."""

    signal: RuntimeSignal
    authority: ResolutionAuthority
    escalation_timeout: float = 30.0
    auto_resolve: str | None = None


@dataclass(frozen=True)
class GovernancePolicy:
    """Determines who resolves what, and when escalation occurs."""

    rules: tuple[GovernanceRule, ...] = ()
    default_authority: ResolutionAuthority = ResolutionAuthority.EITHER
    allow_supervisor_injection: bool = True
    allow_supervisor_cancel: bool = True

    def authority_for(self, signal: RuntimeSignal) -> ResolutionAuthority:
        """Look up the resolution authority for a given signal type."""
        for rule in self.rules:
            if rule.signal == signal:
                return rule.authority
        return self.default_authority

    def rule_for(self, signal: RuntimeSignal) -> GovernanceRule | None:
        """Look up the governance rule for a given signal type."""
        for rule in self.rules:
            if rule.signal == signal:
                return rule
        return None
