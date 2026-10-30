from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.models import WorkflowState

# Read-only path to the live orchestration construction. We only ever read
# this file's text to confirm an adapter is literally wired into Tony's
# runtime; we never import or execute it, and we never write to it.
_TONY_WORKFLOW_RUNTIME_SOURCE = Path(__file__).with_name("tony_workflow_runtime.py")

_REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class CapabilityEvidence:
    """One honestly-labelled maturity signal, always carrying its own evidence.

    Each flag is independently verifiable and must not be inferred from a
    weaker one: a module existing on disk (``implemented``) does not imply a
    test exists (``tested``); a test existing does not imply the live runtime
    actually wires the adapter in (``connected``); being wired in does not
    imply it has ever executed against real evidence (``live_verified``).
    """

    defined: bool
    defined_evidence: str
    implemented: bool
    implemented_evidence: str
    tested: bool
    tested_evidence: str
    connected: bool
    connected_evidence: str
    live_verified: bool
    live_verified_evidence: str
    blocked: bool = False
    blocker: str = ""


@dataclass(frozen=True, slots=True)
class AgencyMapEntry:
    agent_id: str
    title: str
    department: str
    responsibilities: str
    defined_in: str
    capability: CapabilityEvidence
    dependencies: tuple[str, ...] = ()
    active_work: tuple[dict[str, Any], ...] = ()
    last_verified_activity: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "title": self.title,
            "department": self.department,
            "responsibilities": self.responsibilities,
            "defined_in": self.defined_in,
            "status": {
                "defined": self.capability.defined,
                "defined_evidence": self.capability.defined_evidence,
                "implemented": self.capability.implemented,
                "implemented_evidence": self.capability.implemented_evidence,
                "tested": self.capability.tested,
                "tested_evidence": self.capability.tested_evidence,
                "connected": self.capability.connected,
                "connected_evidence": self.capability.connected_evidence,
                "live_verified": self.capability.live_verified,
                "live_verified_evidence": self.capability.live_verified_evidence,
                "blocked": self.capability.blocked,
                "blocker": self.capability.blocker,
            },
            "dependencies": list(self.dependencies),
            "active_work": [dict(item) for item in self.active_work],
            "last_verified_activity": self.last_verified_activity,
        }


@dataclass(frozen=True, slots=True)
class _AgentSpec:
    agent_id: str
    title: str
    department: str
    responsibilities: str
    defined_in: str
    implemented_in: tuple[str, ...]
    tested_in: tuple[str, ...]
    connected_markers: tuple[str, ...]
    canonical_workflow_ids: tuple[str, ...]
    dependencies: tuple[str, ...]
    blocked_marker: str = ""
    blocker: str = ""


_ROSTER: tuple[_AgentSpec, ...] = (
    _AgentSpec(
        agent_id="orchestrator",
        title="Orchestrator (Tony, COO)",
        department="Operations — orchestration",
        responsibilities=(
            "Determines which agent runs next, validates required inputs before "
            "dispatching work, maintains workflow state, detects failures and "
            "retry logic, records completion status, prepares handoffs. Never "
            "creates client deliverables itself."
        ),
        defined_in="agents/orchestrator.md",
        implemented_in=("runtime/tony_workflow_runtime.py", "runtime/workflow_execution_coordinator.py"),
        tested_in=("tests/test_tony_workflow_runtime.py", "tests/test_workflow_execution_coordinator.py"),
        connected_markers=("coordinator = WorkflowExecutionCoordinator(",),
        canonical_workflow_ids=(),
        dependencies=(),
    ),
    _AgentSpec(
        agent_id="research_analyst",
        title="Research Analyst",
        department="Delivery Engine — Growth Blueprint pipeline",
        responsibilities=(
            "Gathers, structures and labels evidence from client inputs, "
            "website/context links and supplied source material for the "
            "Strategy Director. Avoids strategic recommendations."
        ),
        defined_in="agents/research_analyst.md",
        implemented_in=("runtime/research_engine.py", "runtime/research_workflow_adapter.py"),
        tested_in=("tests/test_research_engine.py", "tests/test_research_workflow_adapter.py"),
        connected_markers=("research_adapter=ResearchWorkflowAdapter(",),
        canonical_workflow_ids=("growth_sprint_to_research_engine",),
        dependencies=("Fireflies transcript dispatcher (optional, degrades without it)",),
    ),
    _AgentSpec(
        agent_id="strategy_director",
        title="Strategy Director",
        department="Delivery Engine — Growth Blueprint pipeline",
        responsibilities=(
            "Converts supplied research into the founder- and CMO-ready Growth "
            "Blueprint: strategic diagnosis, positioning, narrative platform and "
            "activation principles, preserving the canonical template structure."
        ),
        defined_in="agents/strategy_director.md",
        implemented_in=("runtime/blueprint_orchestrator.py", "runtime/blueprint_director.py"),
        tested_in=("tests/test_blueprint_orchestrator.py", "tests/test_blueprint_director.py"),
        connected_markers=(
            "document_adapter=document_adapter,",
            "blueprint_director_commission=BlueprintDirectorCommissionBuilder(",
        ),
        canonical_workflow_ids=(
            "research_to_strategic_synthesis",
            "strategic_synthesis_to_strategy_thesis",
            "strategy_thesis_to_growth_blueprint",
            "research_to_growth_blueprint",
        ),
        dependencies=("Approved research evidence from the Research Analyst stage",),
    ),
    _AgentSpec(
        agent_id="campaign_world_generator",
        title="Campaign World Generator",
        department="Delivery Engine — Growth Blueprint pipeline",
        responsibilities=(
            "Translates an approved Growth Blueprint into Campaign World "
            "candidates: campaign territories, narrative tension and emotional "
            "promise, preserving the canonical template structure."
        ),
        defined_in="agents/campaign_world_generator.md",
        implemented_in=("runtime/campaign_world_triage_worker.py",),
        tested_in=("tests/test_campaign_world_triage_worker.py",),
        connected_markers=("campaign_world_triage_adapter=CampaignWorldTriageWorker(),",),
        canonical_workflow_ids=("growth_blueprint_to_campaign_world",),
        dependencies=("Matt's approved Growth Blueprint",),
    ),
    _AgentSpec(
        agent_id="creative_director",
        title="Creative Director",
        department="Delivery Engine — Growth Blueprint pipeline",
        responsibilities=(
            "Translates an approved Campaign World into production-ready "
            "creative direction (the Creative Director's Bible) suitable for "
            "downstream execution, asset production and human creative review."
        ),
        defined_in="agents/creative_director.md",
        implemented_in=(
            "runtime/creative_bible_triage_worker.py",
            "runtime/campaign_production_planning_worker.py",
            "runtime/creative_production_workflow_adapter.py",
        ),
        tested_in=(
            "tests/test_creative_bible_triage_worker.py",
            "tests/test_campaign_production_planning_worker.py",
        ),
        connected_markers=("creative_bible_triage_adapter=CreativeBibleTriageWorker(),",),
        canonical_workflow_ids=("campaign_world_to_creative_bible", "creative_bible_to_asset_production"),
        dependencies=("Matt's approved Campaign World", "A configured 'Creative Production' dispatcher for asset execution"),
        blocked_marker='if "Creative Production" in configured_dispatchers',
        blocker=(
            "Review/triage is wired and live; final asset-production execution is only "
            "constructed when a 'Creative Production' dispatcher is present in the live "
            "environment's configured_dispatchers. No such dispatcher is configured by "
            "default, so execution fails closed rather than silently claiming output."
        ),
    ),
    _AgentSpec(
        agent_id="quality_reviewer",
        title="Quality Reviewer",
        department="Delivery Engine — Growth Blueprint pipeline",
        responsibilities=(
            "Evaluates the completed strategic/creative artefact chain before "
            "client delivery or downstream production. Returns a structured "
            "verdict with evidence, severity and precise revision instructions. "
            "Never rewrites work silently."
        ),
        defined_in="agents/quality_reviewer.md",
        implemented_in=("runtime/workflow_quality.py",),
        tested_in=("tests/test_workflow_quality.py",),
        connected_markers=('"campaign_world_quality_gate": campaign_world_quality_gate,',),
        canonical_workflow_ids=(),
        dependencies=("Output from the specialist stage under review",),
    ),
)


def _repo_path(relative: str) -> Path:
    return _REPO_ROOT / relative


def _file_evidence(paths: tuple[str, ...]) -> tuple[bool, str]:
    if not paths:
        return False, "no path declared"
    existing = [path for path in paths if _repo_path(path).is_file()]
    if len(existing) == len(paths):
        return True, f"found: {', '.join(paths)}"
    if existing:
        missing = [path for path in paths if path not in existing]
        return False, f"found only {', '.join(existing)}; missing {', '.join(missing)}"
    return False, f"none found: {', '.join(paths)}"


def _read_tony_workflow_runtime_source() -> str | None:
    try:
        return _TONY_WORKFLOW_RUNTIME_SOURCE.read_text(encoding="utf-8")
    except OSError:
        return None


def _connected_evidence(source: str | None, markers: tuple[str, ...]) -> tuple[bool, str]:
    if source is None:
        return False, "runtime/tony_workflow_runtime.py could not be read"
    if not markers:
        return False, "no connection marker declared"
    present = [marker for marker in markers if marker in source]
    if len(present) == len(markers):
        return True, f"runtime/tony_workflow_runtime.py contains: {present}"
    missing = [marker for marker in markers if marker not in present]
    return False, f"runtime/tony_workflow_runtime.py is missing: {missing}"


def _blocked_evidence(source: str | None, marker: str) -> bool:
    if not marker or source is None:
        return False
    return marker in source


def _live_verified(
    spec: _AgentSpec,
    states_by_workflow: Mapping[str, tuple[WorkflowState, ...]],
) -> tuple[bool, str, tuple[dict[str, Any], ...], str | None]:
    if not spec.canonical_workflow_ids:
        return False, "this agent has no single canonical workflow_id to verify against", (), None
    matching: list[WorkflowState] = []
    for workflow_id in spec.canonical_workflow_ids:
        matching.extend(states_by_workflow.get(workflow_id, ()))
    if not matching:
        return (
            False,
            f"no persisted WorkflowState was supplied for {spec.canonical_workflow_ids}",
            (),
            None,
        )
    active = [state for state in matching if state.status.value not in {"complete", "failed"}]
    active_work = tuple(
        {
            "run_id": state.run_id,
            "workflow_id": state.workflow_id,
            "client_id": state.client_id,
            "status": state.status.value,
            "current_step": state.current_stage_id,
        }
        for state in sorted(active, key=lambda item: item.updated_at, reverse=True)
    )
    last_updated = max((state.updated_at for state in matching), default=None)
    return (
        True,
        f"{len(matching)} persisted WorkflowState run(s) found for {spec.canonical_workflow_ids}",
        active_work,
        last_updated,
    )


def build_agency_map(
    workflow_states: Iterable[WorkflowState] | None = None,
) -> tuple[AgencyMapEntry, ...]:
    """Project the authoritative agent roster against real repository and run evidence.

    This is a pure, dependency-injected read: nothing is written, nothing is
    executed, and nothing is inferred beyond what the supplied evidence
    actually shows. ``workflow_states`` is optional; when omitted, every
    ``live_verified`` flag is honestly ``False`` with an explicit
    "no evidence supplied" reason rather than guessed.
    """

    source = _read_tony_workflow_runtime_source()
    states_by_workflow: dict[str, tuple[WorkflowState, ...]] = {}
    for state in workflow_states or ():
        states_by_workflow.setdefault(state.workflow_id, ())
        states_by_workflow[state.workflow_id] = (*states_by_workflow[state.workflow_id], state)

    entries = []
    for spec in _ROSTER:
        defined_ok, defined_evidence = _file_evidence((spec.defined_in,))
        implemented_ok, implemented_evidence = _file_evidence(spec.implemented_in)
        tested_ok, tested_evidence = _file_evidence(spec.tested_in)
        connected_ok, connected_evidence = _connected_evidence(source, spec.connected_markers)
        live_ok, live_evidence, active_work, last_verified = _live_verified(spec, states_by_workflow)
        blocked = _blocked_evidence(source, spec.blocked_marker)

        entries.append(
            AgencyMapEntry(
                agent_id=spec.agent_id,
                title=spec.title,
                department=spec.department,
                responsibilities=spec.responsibilities,
                defined_in=spec.defined_in,
                capability=CapabilityEvidence(
                    defined=defined_ok,
                    defined_evidence=defined_evidence,
                    implemented=implemented_ok,
                    implemented_evidence=implemented_evidence,
                    tested=tested_ok,
                    tested_evidence=tested_evidence,
                    connected=connected_ok,
                    connected_evidence=connected_evidence,
                    live_verified=live_ok,
                    live_verified_evidence=live_evidence,
                    blocked=blocked,
                    blocker=spec.blocker if blocked else "",
                ),
                dependencies=spec.dependencies,
                active_work=active_work,
                last_verified_activity=last_verified,
            )
        )
    return tuple(entries)
