from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.models import StageStatus, WorkflowState

# Read-only paths into the live orchestration/capability-registration source.
# This module only ever reads this text to confirm a registration literally
# exists in source; it never imports, executes, or writes to either file.
_WORKER_REGISTRY_SOURCE = Path(__file__).with_name("worker_registry.py")
_TONY_WORKFLOW_RUNTIME_SOURCE = Path(__file__).with_name("tony_workflow_runtime.py")

_REPO_ROOT = Path(__file__).resolve().parent.parent

ROSTER_SCOPE_NOTE = (
    "This roster reflects only the specialist contracts currently defined in "
    "agents/*.md. It is a snapshot of today's authoritative contracts, not a "
    "ceiling or complete catalogue of every specialist capability Narratiive "
    "will ever have. Live workflow activity that does not match any of these "
    "contracts (for example, asset-production execution, the Blueprint "
    "Director editorial pass, or the bounded quality/taste triage stages) is "
    "real and wired, but is deliberately left unattributed here rather than "
    "folded into a contract that does not claim it -- attributing triage to "
    "the Orchestrator or Quality Reviewer without a versioned authority "
    "decision was a confirmed error in an earlier version of this module. "
    "Adding a new agent contract, or deciding who owns an unattributed stage, "
    "is a product-canon change this projector cannot decide on its own."
)

#: Where an Evidence value actually came from. A reader must never treat
#: "supplied_snapshot" as if it were a canonical, independently-verified
#: runtime read -- this module never itself queries a live process or a
#: persisted store; every dynamic signal is only ever as good as what its
#: caller chose to inject, and that is exactly what this field says.
PROVENANCE_REPOSITORY_FILE_CHECK = "repository_file_check"
PROVENANCE_STATIC_SOURCE_SCAN = "static_source_scan"
PROVENANCE_SUPPLIED_SNAPSHOT = "supplied_snapshot"
PROVENANCE_NO_EVIDENCE_SUPPLIED = "no_evidence_supplied"


@dataclass(frozen=True, slots=True)
class Evidence:
    """One honestly-labelled signal with its own supporting evidence text
    and explicit provenance.

    ``value`` is ``True``/``False`` only when real evidence was available to
    decide it; otherwise ``None``. ``None`` must never be rendered as a
    negative -- it means "unverified here", not "no".

    ``provenance`` states where that value actually came from. A caller-
    supplied ``WorkflowState`` or worker-id snapshot is always
    ``supplied_snapshot`` provenance, never implied to be a live or
    canonical read performed by this module itself -- this module has no
    independent access to a running process or a persisted store; it only
    ever evaluates what was handed to it.
    """

    value: bool | None
    evidence: str
    provenance: str


@dataclass(frozen=True, slots=True)
class CapabilityEvidence:
    """Six independently-verifiable maturity signals. None may be inferred
    from another: a module existing on disk (``implemented``) does not imply
    a test exists (``tested``); a test existing does not imply the capability
    is registered in source (``configured``); being registered in source does
    not imply the live, running process actually has it active
    (``runtime_connected`` -- a static source-text match is NOT a runtime
    connectivity check and must never be presented as proof an agent is
    operational); being configured or runtime-connected does not imply it has
    ever executed against real evidence (``live_verified``).
    """

    defined: Evidence
    implemented: Evidence
    tested: Evidence
    configured: Evidence
    runtime_connected: Evidence
    live_verified: Evidence
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
        def _evidence(item: Evidence) -> dict[str, Any]:
            return {"value": item.value, "evidence": item.evidence, "provenance": item.provenance}

        return {
            "agent_id": self.agent_id,
            "title": self.title,
            "department": self.department,
            "responsibilities": self.responsibilities,
            "defined_in": self.defined_in,
            "status": {
                "defined": _evidence(self.capability.defined),
                "implemented": _evidence(self.capability.implemented),
                "tested": _evidence(self.capability.tested),
                "configured": _evidence(self.capability.configured),
                "runtime_connected": _evidence(self.capability.runtime_connected),
                "live_verified": _evidence(self.capability.live_verified),
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
    implemented_note: str
    tested_in: tuple[str, ...]
    # ALL markers must be present for configured=True -- a partial match
    # must never be reported as configured (a confirmed defect in an
    # earlier version of this module, found in independent review).
    configured_markers: tuple[str, ...]
    configured_note: str
    worker_ids: tuple[str, ...]
    # (workflow_id, stage_id) pairs this agent's own contract can defensibly
    # claim -- a workflow can have stages owned by a different specialist,
    # or by no current specialist at all, so attribution is always at stage
    # granularity, never whole-workflow, and is never assigned to an agent
    # whose contract does not itself claim the responsibility.
    canonical_stage_refs: tuple[tuple[str, str], ...]
    dependencies: tuple[str, ...]


_ROSTER: tuple[_AgentSpec, ...] = (
    _AgentSpec(
        agent_id="orchestrator",
        title="Orchestrator (Tony, COO)",
        department="Operations — orchestration",
        responsibilities=(
            "Determines which agent runs next, validates required inputs before "
            "dispatching work, maintains workflow state, detects failures and "
            "retry logic, records completion status, prepares handoffs. Never "
            "creates client deliverables itself. This projector does not "
            "attribute the bounded quality/taste triage stages to the "
            "Orchestrator: agents/orchestrator.md does not claim them, and an "
            "earlier version of this module wrongly did -- see "
            "ROSTER_SCOPE_NOTE."
        ),
        defined_in="agents/orchestrator.md",
        implemented_in=("runtime/tony_workflow_runtime.py", "runtime/workflow_execution_coordinator.py"),
        implemented_note="orchestration core only",
        tested_in=("tests/test_tony_workflow_runtime.py", "tests/test_workflow_execution_coordinator.py"),
        configured_markers=("coordinator = WorkflowExecutionCoordinator(",),
        configured_note="static source match only; does not confirm the running process executed any of this",
        worker_ids=(),
        canonical_stage_refs=(),
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
        implemented_note="dedicated, agent-specific module",
        tested_in=("tests/test_research_engine.py", "tests/test_research_workflow_adapter.py"),
        configured_markers=('worker_id="narratiive-research-engine"',),
        configured_note="static source match only; does not confirm the running process executed any of this",
        worker_ids=("narratiive-research-engine",),
        canonical_stage_refs=(("growth_sprint_to_research_engine", "orchestrate_research"),),
        dependencies=("Fireflies transcript dispatcher (optional, degrades without it)",),
    ),
    _AgentSpec(
        agent_id="strategy_director",
        title="Strategy Director",
        department="Delivery Engine — Growth Blueprint pipeline",
        responsibilities=(
            "Converts supplied research into the Growth Blueprint's strategic "
            "diagnosis, positioning, narrative platform and activation "
            "principles. This projector does not attribute the subsequent "
            "editorial 'director' pass or the review stage that follow it in "
            "strategy_thesis_to_growth_blueprint to Strategy Director -- no "
            "agents/*.md contract currently names an owner for the director "
            "pass, and the review stage matches Quality Reviewer's contract "
            "instead. Discovery Preparation (prepare_discovery) IS attributed "
            "here as an explicit ownership-assignment decision, not a "
            "reinterpretation of agents/strategy_director.md's own text: that "
            "contract names only Growth Blueprint population, but the stage "
            "runs through the identical strategic_reasoning capability and "
            "turns evidence into forward strategic judgement, the same work "
            "the contract already describes for the Blueprint itself. This is "
            "the one accountability assignment made in this round; see "
            "docs/engineering/campaign-engine-foundation.md and the project "
            "conversation record dated 2026-10-30 for the decision basis."
        ),
        defined_in="agents/strategy_director.md",
        implemented_in=("runtime/worker_registry.py",),
        implemented_note=(
            "no dedicated per-agent module exists; this stage is served by the "
            "single shared, conditionally-registered Claude capability worker "
            "(worker_id=claude-anthropic) that also serves Campaign World "
            "Generator's and Creative Director's generation stages"
        ),
        tested_in=("tests/test_worker_registry.py",),
        configured_markers=('worker_id="claude-anthropic"', '"strategic_reasoning"'),
        configured_note=(
            "static source match only; this worker is shared across three specialists' "
            "generation stages and is only registered when a 'Claude' dispatcher name is "
            "present in the live process's dispatcher map -- a condition this static check "
            "cannot observe"
        ),
        worker_ids=("claude-anthropic",),
        canonical_stage_refs=(
            ("blueprint_lite_to_discovery_preparation", "prepare_discovery"),
            ("research_to_strategic_synthesis", "prepare_strategic_synthesis"),
            ("strategic_synthesis_to_strategy_thesis", "prepare_strategy_thesis"),
            ("strategy_thesis_to_growth_blueprint", "prepare_growth_blueprint"),
        ),
        dependencies=("Approved research evidence from the Research Analyst stage", "A configured 'Claude' dispatcher"),
    ),
    _AgentSpec(
        agent_id="campaign_world_generator",
        title="Campaign World Generator",
        department="Delivery Engine — Growth Blueprint pipeline",
        responsibilities=(
            "Translates an approved Growth Blueprint into Campaign World "
            "candidates: campaign territories, narrative tension and emotional "
            "promise. This projector does not attribute the subsequent bounded "
            "taste triage of those candidates to Campaign World Generator -- "
            "no agents/*.md contract currently names an owner for that triage "
            "stage; see ROSTER_SCOPE_NOTE."
        ),
        defined_in="agents/campaign_world_generator.md",
        implemented_in=("runtime/worker_registry.py",),
        implemented_note=(
            "no dedicated per-agent module exists; this stage is served by the "
            "shared Claude capability worker (worker_id=claude-anthropic), not by "
            "runtime/campaign_world_triage_worker.py -- that module implements the "
            "unattributed taste-triage stage, a separate stage this agent's contract "
            "does not claim"
        ),
        tested_in=("tests/test_worker_registry.py",),
        configured_markers=('worker_id="claude-anthropic"', '"strategic_reasoning"'),
        configured_note=(
            "static source match only; this worker is shared across three specialists' "
            "generation stages and is only registered when a 'Claude' dispatcher name is "
            "present in the live process's dispatcher map -- a condition this static check "
            "cannot observe"
        ),
        worker_ids=("claude-anthropic",),
        canonical_stage_refs=(("growth_blueprint_to_campaign_world", "generate_campaign_world"),),
        dependencies=("Matt's approved Growth Blueprint", "A configured 'Claude' dispatcher"),
    ),
    _AgentSpec(
        agent_id="creative_director",
        title="Creative Director",
        department="Delivery Engine — Growth Blueprint pipeline",
        responsibilities=(
            "Translates an approved Campaign World into the Creative Director's "
            "Bible. This projector does not attribute the subsequent bounded "
            "taste triage of the Bible, or the downstream production-planning/"
            "asset-execution stages in creative_bible_to_asset_production, to "
            "Creative Director -- no agents/*.md contract currently names an "
            "owner for either."
        ),
        defined_in="agents/creative_director.md",
        implemented_in=("runtime/worker_registry.py",),
        implemented_note=(
            "no dedicated per-agent module exists; this stage is served by the "
            "shared Claude capability worker (worker_id=claude-anthropic)"
        ),
        tested_in=("tests/test_worker_registry.py",),
        configured_markers=('worker_id="claude-anthropic"', '"copy_drafting"'),
        configured_note=(
            "static source match only; this worker is shared across three specialists' "
            "generation stages and is only registered when a 'Claude' dispatcher name is "
            "present in the live process's dispatcher map -- a condition this static check "
            "cannot observe"
        ),
        worker_ids=("claude-anthropic",),
        canonical_stage_refs=(("campaign_world_to_creative_bible", "prepare_creative_bible"),),
        dependencies=("Matt's approved Campaign World", "A configured 'Claude' dispatcher"),
    ),
    _AgentSpec(
        agent_id="quality_reviewer",
        title="Quality Reviewer",
        department="Delivery Engine — Growth Blueprint pipeline",
        responsibilities=(
            "Evaluates the completed strategic/creative artefact chain before "
            "client delivery or downstream production. Returns a structured "
            "verdict with evidence, severity and precise revision instructions. "
            "Never rewrites work silently. This projector does not attribute "
            "the Orchestrator's bounded quality/taste triage stages to Quality "
            "Reviewer either, even though both perform a quality judgement on "
            "the same artefacts -- they are distinct responsibilities per "
            "docs/engineering/campaign-engine-foundation.md, and only the "
            "stage this agent's own contract matches is claimed here."
        ),
        defined_in="agents/quality_reviewer.md",
        implemented_in=("runtime/workflow_quality.py", "runtime/senior_strategist_review_worker.py"),
        implemented_note=(
            "deterministic structural quality-gate functions evaluated in-process "
            "(not dispatched through the capability worker registry) plus the "
            "dedicated senior-strategist review stage, which is dispatched through it"
        ),
        tested_in=("tests/test_workflow_quality.py", "tests/test_senior_strategist_review_worker.py"),
        configured_markers=(
            '"campaign_world_quality_gate": campaign_world_quality_gate,',
            'worker_id="narratiive-senior-strategist-reviewer"',
        ),
        configured_note="static source match only; does not confirm the running process executed any of this",
        worker_ids=("narratiive-senior-strategist-reviewer",),
        canonical_stage_refs=(("strategy_thesis_to_growth_blueprint", "review_growth_blueprint"),),
        dependencies=("Output from the specialist stage under review",),
    ),
)


def _repo_path(relative: str) -> Path:
    return _REPO_ROOT / relative


def _file_evidence(paths: tuple[str, ...], note: str = "") -> Evidence:
    if not paths:
        return Evidence(False, "no path declared", PROVENANCE_REPOSITORY_FILE_CHECK)
    existing = [path for path in paths if _repo_path(path).is_file()]
    suffix = f" ({note})" if note else ""
    if len(existing) == len(paths):
        return Evidence(True, f"found: {', '.join(paths)}{suffix}", PROVENANCE_REPOSITORY_FILE_CHECK)
    if existing:
        missing = [path for path in paths if path not in existing]
        return Evidence(
            False,
            f"found only {', '.join(existing)}; missing {', '.join(missing)}{suffix}",
            PROVENANCE_REPOSITORY_FILE_CHECK,
        )
    return Evidence(False, f"none found: {', '.join(paths)}{suffix}", PROVENANCE_REPOSITORY_FILE_CHECK)


def _read_combined_source() -> str | None:
    try:
        runtime_text = _TONY_WORKFLOW_RUNTIME_SOURCE.read_text(encoding="utf-8")
        registry_text = _WORKER_REGISTRY_SOURCE.read_text(encoding="utf-8")
    except OSError:
        return None
    return runtime_text + "\n" + registry_text


def _configured_evidence(source: str | None, markers: tuple[str, ...], note: str) -> Evidence:
    """configured=True only when EVERY declared marker is present.

    A partial match must never be reported as configured -- that was a
    confirmed defect in an earlier version of this module, found in
    independent review. Evidence always lists exactly which markers were
    found and which were missing, so a reader never has to trust a single
    collapsed boolean.
    """

    if source is None:
        return Evidence(None, "source files could not be read; unverified", PROVENANCE_STATIC_SOURCE_SCAN)
    if not markers:
        return Evidence(False, "no configuration marker declared for this agent", PROVENANCE_STATIC_SOURCE_SCAN)
    present = [marker for marker in markers if marker in source]
    missing = [marker for marker in markers if marker not in present]
    all_present = not missing
    detail = f"found {present}" + (f"; missing {missing}" if missing else "")
    return Evidence(all_present, f"{detail} ({note})", PROVENANCE_STATIC_SOURCE_SCAN)


def _runtime_connected_evidence(
    worker_ids: tuple[str, ...],
    live_worker_ids: frozenset[str] | None,
) -> Evidence:
    if not worker_ids:
        return Evidence(
            None,
            "this agent's capability is not dispatched through the capability worker "
            "registry, so there is no live worker_id to verify against",
            PROVENANCE_NO_EVIDENCE_SUPPLIED,
        )
    if live_worker_ids is None:
        return Evidence(
            None,
            f"no worker-registry snapshot was supplied to verify {worker_ids} against; "
            "a static source match is not a runtime connectivity check",
            PROVENANCE_NO_EVIDENCE_SUPPLIED,
        )
    present = [worker_id for worker_id in worker_ids if worker_id in live_worker_ids]
    if present:
        return Evidence(
            True,
            f"found in the supplied worker-registry snapshot: {present} "
            "(the snapshot's own liveness/canonicity is the caller's evidence, not independently verified here)",
            PROVENANCE_SUPPLIED_SNAPSHOT,
        )
    return Evidence(
        False,
        f"none of {worker_ids} were present in the supplied worker-registry snapshot",
        PROVENANCE_SUPPLIED_SNAPSHOT,
    )


def _live_verified(
    spec: _AgentSpec,
    workflow_states: Iterable[WorkflowState] | None,
) -> tuple[Evidence, tuple[dict[str, Any], ...], str | None]:
    if not spec.canonical_stage_refs:
        return (
            Evidence(
                None,
                "this agent has no single canonical (workflow_id, stage_id) pair to verify against",
                PROVENANCE_NO_EVIDENCE_SUPPLIED,
            ),
            (),
            None,
        )
    if workflow_states is None:
        return (
            Evidence(
                None,
                "no WorkflowState snapshot was supplied to verify this agent's stage against",
                PROVENANCE_NO_EVIDENCE_SUPPLIED,
            ),
            (),
            None,
        )
    states = tuple(workflow_states)
    completed_matches: list[tuple[WorkflowState, str]] = []
    active_matches: list[tuple[WorkflowState, str]] = []
    for state in states:
        for workflow_id, stage_id in spec.canonical_stage_refs:
            if state.workflow_id != workflow_id:
                continue
            stage = next((item for item in state.stages if item.stage_id == stage_id), None)
            if stage is None:
                continue
            if stage.status == StageStatus.COMPLETED:
                completed_matches.append((state, stage_id))
            elif stage.status == StageStatus.RUNNING:
                active_matches.append((state, stage_id))
    if not completed_matches and not active_matches:
        return (
            Evidence(
                False,
                f"no state in the supplied WorkflowState snapshot has a completed or running stage "
                f"matching {spec.canonical_stage_refs}",
                PROVENANCE_SUPPLIED_SNAPSHOT,
            ),
            (),
            None,
        )
    active_work = tuple(
        {
            "run_id": state.run_id,
            "workflow_id": state.workflow_id,
            "stage_id": stage_id,
            "client_id": state.client_id,
        }
        for state, stage_id in sorted(active_matches, key=lambda item: item[0].updated_at, reverse=True)
    )
    all_matches = [state for state, _ in (*completed_matches, *active_matches)]
    last_updated = max((state.updated_at for state in all_matches), default=None)
    return (
        Evidence(
            True,
            f"{len(completed_matches)} completed and {len(active_matches)} running stage match(es) found "
            f"in the supplied WorkflowState snapshot for {spec.canonical_stage_refs}",
            PROVENANCE_SUPPLIED_SNAPSHOT,
        ),
        active_work,
        last_updated,
    )


def build_agency_map(
    workflow_states: Iterable[WorkflowState] | None = None,
    *,
    live_worker_ids: frozenset[str] | None = None,
) -> tuple[AgencyMapEntry, ...]:
    """Project the authoritative agent roster against real repository and run evidence.

    This is a pure, dependency-injected read: nothing is written, nothing is
    executed, and nothing is inferred beyond what the supplied evidence
    actually shows. Neither parameter is independently verified by this
    module as live or canonical -- see ``Evidence.provenance``.

    - ``workflow_states`` is optional. Omitting it (``None``) means every
      ``live_verified`` flag is honestly ``None`` ("unverified -- no snapshot
      supplied"), never collapsed into ``False``. Passing an explicit
      (possibly empty) collection means the agent's stage was checked against
      it and genuinely not found, which is reported as ``False`` with
      ``supplied_snapshot`` provenance.
    - ``live_worker_ids`` is optional and represents a snapshot of worker_ids
      a caller observed in a capability worker registry. Omitting it means
      every ``runtime_connected`` flag is honestly ``None`` ("unverified"),
      never inferred from the static ``configured`` source match. This
      module does not read any live registry itself.

    Attribution is always at (workflow_id, stage_id) granularity, and only
    to an agent whose own agents/*.md contract claims that exact stage. A
    workflow can have stages owned by a different specialist, or by no
    current specialist at all (see ROSTER_SCOPE_NOTE); this function never
    guesses an owner for an unattributed stage.
    """

    source = _read_combined_source()

    entries = []
    for spec in _ROSTER:
        defined = _file_evidence((spec.defined_in,))
        implemented = _file_evidence(spec.implemented_in, spec.implemented_note)
        tested = _file_evidence(spec.tested_in)
        configured = _configured_evidence(source, spec.configured_markers, spec.configured_note)
        runtime_connected = _runtime_connected_evidence(spec.worker_ids, live_worker_ids)
        live_verified, active_work, last_verified = _live_verified(spec, workflow_states)

        entries.append(
            AgencyMapEntry(
                agent_id=spec.agent_id,
                title=spec.title,
                department=spec.department,
                responsibilities=spec.responsibilities,
                defined_in=spec.defined_in,
                capability=CapabilityEvidence(
                    defined=defined,
                    implemented=implemented,
                    tested=tested,
                    configured=configured,
                    runtime_connected=runtime_connected,
                    live_verified=live_verified,
                ),
                dependencies=spec.dependencies,
                active_work=active_work,
                last_verified_activity=last_verified,
            )
        )
    return tuple(entries)
