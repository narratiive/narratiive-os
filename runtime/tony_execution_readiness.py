from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from runtime.tony_dispatch_adapters import SUPPORTED_DISPATCH_WORKERS, _env_key


@dataclass(frozen=True, slots=True)
class WorkerReadiness:
    worker: str
    configured: bool
    mode: str
    missing: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "worker": self.worker,
            "configured": self.configured,
            "mode": self.mode,
            "missing": list(self.missing),
        }


@dataclass(frozen=True, slots=True)
class ExecutionReadinessReport:
    ready: bool
    configured_workers: tuple[str, ...]
    missing_workers: tuple[str, ...]
    workers: tuple[WorkerReadiness, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "configured_workers": list(self.configured_workers),
            "missing_workers": list(self.missing_workers),
            "workers": [worker.to_dict() for worker in self.workers],
        }


@dataclass(frozen=True, slots=True)
class ControlledIntegration:
    surface: str
    configured: bool
    autonomous_operations: tuple[str, ...]
    approval_gated_operations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "surface": self.surface,
            "configured": self.configured,
            "autonomous_operations": list(self.autonomous_operations),
            "approval_gated_operations": list(self.approval_gated_operations),
        }


# These are the live surfaces required by the end-to-end commercial and delivery flow.
REQUIRED_LIVE_WORKERS = (
    "Claude",
    "Gmail",
    "Google Calendar",
    "Google Drive",
    "Notion",
    "Fireflies",
)


def build_execution_readiness_report(environ: Mapping[str, str]) -> ExecutionReadinessReport:
    workers = tuple(_worker_readiness(worker, environ) for worker in REQUIRED_LIVE_WORKERS)
    configured = tuple(item.worker for item in workers if item.configured)
    missing = tuple(item.worker for item in workers if not item.configured)
    return ExecutionReadinessReport(
        ready=not missing,
        configured_workers=configured,
        missing_workers=missing,
        workers=workers,
    )


def build_controlled_integration_report(environ: Mapping[str, str]) -> tuple[ControlledIntegration, ...]:
    """Describe existing adapter operations without implying configuration or execution."""
    operations = {
        "Gmail": (
            ("read_verified_thread", "monitor_reply"),
            ("send_reviewed_email",),
        ),
        "Google Calendar": (
            ("read_availability",),
            ("create_recipient_confirmed_meeting",),
        ),
        "Notion": (
            ("read_business_pipeline",),
            ("project_workflow_state", "update_verified_business_transition"),
        ),
    }
    return tuple(
        ControlledIntegration(
            surface=surface,
            configured=_worker_readiness(surface, environ).configured,
            autonomous_operations=autonomous,
            approval_gated_operations=gated,
        )
        for surface, (autonomous, gated) in operations.items()
    )


def _worker_readiness(worker: str, environ: Mapping[str, str]) -> WorkerReadiness:
    if worker not in SUPPORTED_DISPATCH_WORKERS:
        raise ValueError(f"unsupported dispatcher worker: {worker}")

    key = _env_key(worker)
    url_key = f"TONY_DISPATCH_{key}_URL"
    token_key = f"TONY_DISPATCH_{key}_TOKEN"
    url = str(environ.get(url_key, "")).strip()
    if url:
        return WorkerReadiness(worker=worker, configured=True, mode="http", missing=())

    if worker == "Claude":
        mode = str(environ.get("TONY_DISPATCH_CLAUDE_MODE", "")).strip().casefold()
        if mode == "anthropic_api":
            missing: list[str] = []
            if not str(environ.get("TONY_DISPATCH_CLAUDE_MODEL", "")).strip():
                missing.append("TONY_DISPATCH_CLAUDE_MODEL")
            if not str(
                environ.get("TONY_DISPATCH_CLAUDE_API_KEY")
                or environ.get("ANTHROPIC_API_KEY")
                or ""
            ).strip():
                missing.append("ANTHROPIC_API_KEY or TONY_DISPATCH_CLAUDE_API_KEY")
            return WorkerReadiness(
                worker=worker,
                configured=not missing,
                mode="anthropic_api",
                missing=tuple(missing),
            )
        return WorkerReadiness(
            worker=worker,
            configured=False,
            mode="unconfigured",
            missing=(
                "TONY_DISPATCH_CLAUDE_URL, or TONY_DISPATCH_CLAUDE_MODE=anthropic_api + TONY_DISPATCH_CLAUDE_MODEL + API key",
            ),
        )

    # Tokens are optional because some local dispatch endpoints are loopback-only or authenticate elsewhere.
    return WorkerReadiness(
        worker=worker,
        configured=False,
        mode="unconfigured",
        missing=(url_key,),
    )


def render_execution_readiness(report: ExecutionReadinessReport) -> str:
    lines = ["Tony live execution readiness: READY" if report.ready else "Tony live execution readiness: CONFIGURATION REQUIRED"]
    for worker in report.workers:
        if worker.configured:
            lines.append(f"OK — {worker.worker} ({worker.mode})")
        else:
            lines.append(f"MISSING — {worker.worker}: {', '.join(worker.missing)}")
    if not report.ready:
        lines.append("No missing credential or endpoint is inferred as configured. Add only the variables for the workers you actually operate, then redeploy Tony and rerun this check.")
    return "\n".join(lines)
