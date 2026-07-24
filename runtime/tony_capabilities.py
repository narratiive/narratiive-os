from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class TonyCapability:
    command: str
    purpose: str
    category: str
    requires: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()

    def to_dict(self, configured_features: Iterable[str] = ()) -> dict[str, Any]:
        configured = set(configured_features)
        missing = [requirement for requirement in self.requires if requirement not in configured]
        return {
            "command": self.command,
            "purpose": self.purpose,
            "category": self.category,
            "aliases": list(self.aliases),
            "requires": list(self.requires),
            "available": not missing,
            "missing_requirements": missing,
        }


CAPABILITIES: tuple[TonyCapability, ...] = (
    TonyCapability("/health", "Validate canonical repository state and runtime integrity.", "system"),
    TonyCapability("/status", "Summarise active campaigns and repository blockers.", "oversight", aliases=("/progress",)),
    TonyCapability("/clients", "List clients and their active campaign counts.", "oversight"),
    TonyCapability("/client <name>", "Show campaign state and next actions for one client.", "oversight"),
    TonyCapability("/next", "Select the highest-priority actionable campaign.", "orchestration", aliases=("/continue",)),
    TonyCapability(
        "/mission",
        "Show Mission Control: blockers, approvals, connections and next work.",
        "oversight",
        requires=("mission_control",),
        aliases=("/brief", "/mission_control"),
    ),
    TonyCapability(
        "/github",
        "Show live pull requests, active issues, blockers, Matt reviews and changes.",
        "oversight",
        requires=("github",),
    ),
    TonyCapability(
        "/history [filter]",
        "Show recent autonomous execution records.",
        "audit",
        requires=("execution_journal",),
    ),
    TonyCapability(
        "/explain <decision-id>",
        "Explain why an autonomous decision was made and what it produced.",
        "audit",
        requires=("execution_journal",),
    ),
    TonyCapability(
        "/diagnostics",
        "Identify the exact unhealthy runtime component without using an LLM.",
        "system",
        requires=("diagnostics",),
        aliases=("/doctor",),
    ),
)


class TonyCapabilityRegistry:
    """Single machine-readable catalogue of Tony's operator-facing abilities."""

    def __init__(self, capabilities: Iterable[TonyCapability] = CAPABILITIES) -> None:
        self.capabilities = tuple(capabilities)
        commands = [capability.command for capability in self.capabilities]
        if len(commands) != len(set(commands)):
            raise ValueError("capability commands must be unique")

    def snapshot(self, configured_features: Iterable[str] = ()) -> dict[str, Any]:
        entries = [capability.to_dict(configured_features) for capability in self.capabilities]
        available = sum(1 for entry in entries if entry["available"])
        return {
            "status": "ready" if available == len(entries) else "partial",
            "available_count": available,
            "total_count": len(entries),
            "capabilities": entries,
        }

    def telegram_summary(self, configured_features: Iterable[str] = ()) -> str:
        snapshot = self.snapshot(configured_features)
        lines = [f"Tony capabilities: {snapshot['available_count']}/{snapshot['total_count']} available"]
        for entry in snapshot["capabilities"]:
            marker = "✓" if entry["available"] else "–"
            lines.append(f"{marker} {entry['command']} — {entry['purpose']}")
        return "\n".join(lines)
