from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from runtime.models import WorkflowState
from runtime.workflow_registry import WorkflowRegistry


@dataclass(frozen=True, slots=True)
class CapabilityEvidence:
    capability: str
    status: str
    evidence: tuple[str, ...]
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AcceptanceProgrammeStatusBuilder:
    """Project acceptance truth from existing runtime evidence.

    This is deliberately read-only. Workflow snapshots, append-only events,
    deployment receipts and provider receipts remain authoritative; this view
    does not create another lifecycle state store.
    """

    WORKFLOW_CAPABILITIES = (
        ("Blueprint Lite", "growth_diagnostic_to_blueprint_lite"),
        ("Discovery", "blueprint_lite_to_discovery_preparation"),
        ("Growth Sprint proposal", "discovery_evidence_to_growth_sprint_proposal"),
        ("Research", "growth_sprint_to_research_engine"),
        ("Growth Blueprint strategy", "research_to_growth_blueprint"),
        ("Growth Blueprint presentation", "growth_blueprint_deliverable_production"),
    )
    SCENARIO_SEQUENCE = (
        ("Blueprint Lite", "growth_diagnostic_to_blueprint_lite"),
        ("Discovery", "blueprint_lite_to_discovery_preparation"),
        ("Growth Sprint proposal", "discovery_evidence_to_growth_sprint_proposal"),
        ("Research", "growth_sprint_to_research_engine"),
        ("Strategic synthesis", "research_to_strategic_synthesis"),
        ("Strategy Thesis", "strategic_synthesis_to_strategy_thesis"),
        ("Growth Blueprint strategy", "strategy_thesis_to_growth_blueprint"),
        ("Growth Blueprint presentation", "growth_blueprint_deliverable_production"),
    )

    def __init__(self, registry: WorkflowRegistry) -> None:
        self.registry = registry
        self.workflow_ids = {definition.workflow_id for definition in registry.all()}

    def build(
        self,
        states: Iterable[WorkflowState],
        *,
        scenario_client_id: str,
        deployment: Mapping[str, Any],
        service_health: Iterable[Mapping[str, Any]] = (),
        conversation_work: Iterable[Mapping[str, Any]] = (),
        recovery: Mapping[str, Any] | None = None,
        attention: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        all_states = tuple(states)
        scenario = tuple(state for state in all_states if state.client_id == scenario_client_id)
        if not scenario:
            raise ValueError("acceptance scenario has no persisted workflow runs")

        health = tuple(dict(item) for item in service_health)
        conversations = tuple(dict(item) for item in conversation_work)
        recovery_evidence = dict(recovery or {})
        attention_evidence = dict(attention or {})
        capabilities = self._capabilities(
            all_states,
            scenario,
            health,
            conversations,
            recovery_evidence,
            attention_evidence,
            deployment,
        )
        checkpoint = self._last_verified_checkpoint(scenario)
        failing = self._failing_transition(scenario)
        thesis_present = {
            "research_to_strategic_synthesis",
            "strategic_synthesis_to_strategy_thesis",
            "strategy_thesis_to_growth_blueprint",
        }.issubset(self.workflow_ids)
        research_complete = any(
            state.workflow_id == "growth_sprint_to_research_engine"
            and state.status.value == "complete"
            and self._quality_passed(state)
            for state in scenario
        )
        conflicts: list[dict[str, Any]] = []
        requires_matt: list[dict[str, Any]] = []
        if research_complete and not thesis_present:
            research_definition = self.registry.resolve("growth_sprint_to_research_engine")
            conflicts.append(
                {
                    "code": "strategy_thesis_stage_missing",
                    "observed": research_definition.next_workflow_id,
                    "expected": "research_to_strategic_synthesis",
                    "classification": "product_canon",
                }
            )
            requires_matt.append(
                {
                    "decision": (
                        "Define and approve the canonical Strategic Synthesis and "
                        "Strategy Thesis contract for Gate 3."
                    ),
                    "reason": "The deployed registry currently routes Research directly to Growth Blueprint.",
                }
            )

        next_unimplemented = next(
            (
                name
                for name, workflow_id in self.SCENARIO_SEQUENCE
                if workflow_id not in self.workflow_ids
            ),
            None,
        )
        current_stage = checkpoint.get("capability") if checkpoint else "No verified checkpoint"
        if requires_matt:
            current_stage = "Strategy Thesis product-canon gate"

        return {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "deployed_revision": str(deployment.get("deployed_revision") or ""),
            "deployment_status": str(deployment.get("status") or "unknown"),
            "current_acceptance_scenario": scenario_client_id,
            "current_stage": current_stage,
            "last_verified_checkpoint": checkpoint,
            "failing": failing,
            "being_repaired": None,
            "requires_matt": requires_matt,
            "next_unimplemented_capability": next_unimplemented,
            "architectural_conflicts": conflicts,
            "service_health": list(health),
            "capabilities": [item.as_dict() for item in capabilities],
            "source_of_truth": {
                "workflow": "Narratiive OS persisted workflow snapshots and append-only events",
                "deployment": "Narratiive OS deployment receipt",
                "recovery": "Narratiive OS recovery receipt",
                "attention": "Narratiive OS live attention-acceptance receipt",
                "projection_only": True,
            },
        }

    def _capabilities(
        self,
        all_states: tuple[WorkflowState, ...],
        scenario: tuple[WorkflowState, ...],
        health: tuple[dict[str, Any], ...],
        conversations: tuple[dict[str, Any], ...],
        recovery: Mapping[str, Any],
        attention: Mapping[str, Any],
        deployment: Mapping[str, Any],
    ) -> tuple[CapabilityEvidence, ...]:
        result: list[CapabilityEvidence] = []
        healthy_services = tuple(
            str(item.get("name") or "service")
            for item in health
            if item.get("healthy") is True
        )
        result.append(
            CapabilityEvidence(
                "Tony ordinary conversation",
                "LIVE_PROVEN" if any(item.get("state") == "completed" for item in conversations) else "IMPLEMENTED",
                tuple(
                    f"conversation_work:{item.get('work_id')}"
                    for item in conversations
                    if item.get("state") == "completed"
                )[-3:] or ("implementation:runtime/tony_conversation_work.py",),
            )
        )
        telegram_evidence = self._telegram_evidence(scenario, conversations)
        result.append(
            CapabilityEvidence(
                "Telegram ingress",
                "LIVE_PROVEN" if telegram_evidence else "IMPLEMENTED",
                telegram_evidence or ("implementation:openclaw/tony_live_bridge.py",),
            )
        )
        promised = tuple(
            f"workflow_run:{state.run_id}"
            for state in scenario
            if isinstance(state.input_payload.get("_promised_work"), Mapping)
            and state.promised_work_delivery.get("status") == "delivered"
        )
        result.append(
            CapabilityEvidence(
                "Long-running work",
                "LIVE_PROVEN" if promised else "IMPLEMENTED",
                promised or ("implementation:runtime/tony_promised_work.py",),
            )
        )
        recovery_proven = self._recovery_proven(recovery, deployment, healthy_services)
        attention_proven = self._attention_proven(attention, deployment)
        recovery_evidence = (
            (
                f"recovery:{recovery.get('attempted_at')}",
                *(f"restarted:{label}" for label in recovery.get("restarted_services", [])),
            )
            if recovery_proven
            else ("implementation:runtime/run_service.py", "implementation:scripts/recover_tony_services.py")
        )
        result.extend(
            (
                CapabilityEvidence(
                    "Runtime services",
                    "LIVE_PROVEN" if healthy_services else "UNPROVEN",
                    tuple(f"health:{name}" for name in healthy_services),
                ),
                CapabilityEvidence(
                    "Restart/recovery",
                    "LIVE_PROVEN" if recovery_proven else "IMPLEMENTED",
                    tuple(recovery_evidence),
                    "" if recovery_proven else "No valid live recovery receipt matches the deployed revision and current healthy services.",
                ),
                CapabilityEvidence(
                    "Attention suppression",
                    "LIVE_PROVEN" if attention_proven else "IMPLEMENTED",
                    (
                        (
                            f"attention:{attention.get('checked_at')}",
                            f"hidden_records:{attention.get('hidden_lead_count')}",
                            f"visible_records:{attention.get('visible_lead_count')}",
                            f"delivery:{attention.get('duplicate_status')}",
                        )
                        if attention_proven
                        else ("implementation:runtime/lead_attention.py",)
                    ),
                    "" if attention_proven else "No valid live attention receipt matches the deployed revision.",
                ),
            )
        )

        for capability, workflow_id in self.WORKFLOW_CAPABILITIES:
            evidence = self._workflow_capability(all_states, workflow_id)
            if capability == "Discovery" and evidence.status != "LIVE_PROVEN":
                recovered = tuple(
                    f"workflow_input:{state.run_id}:discovery_evidence"
                    for state in scenario
                    if state.workflow_id == "discovery_evidence_to_growth_sprint_proposal"
                    and isinstance(state.input_payload.get("discovery_evidence"), Mapping)
                )
                if recovered:
                    evidence = CapabilityEvidence(
                        capability,
                        "LIVE_PROVEN",
                        recovered,
                        "Discovery evidence was recovered and used; the dedicated preparation run was not replayed.",
                    )
            result.append(evidence)

        result.append(self._additional_research_capability(all_states))
        result.extend(
            (
                self._missing_workflow_capability(
                    "Strategic synthesis", "research_to_strategic_synthesis"
                ),
                self._missing_workflow_capability(
                    "Strategy Thesis", "strategic_synthesis_to_strategy_thesis"
                ),
            )
        )
        review = tuple(
            f"gmail_receipt:{state.run_id}:{receipt.get('receipt', {}).get('message_id')}"
            for state in scenario
            for receipt in state.external_action_receipts
            if isinstance(receipt.get("receipt"), Mapping)
            and receipt["receipt"].get("kind") == "internal_artifact_review_delivery"
            and receipt["receipt"].get("message_id")
        )
        approvals = tuple(
            f"approval:{state.run_id}:{item.get('approver')}"
            for state in scenario
            for item in state.approval_history
            if str(item.get("approver") or "").startswith("telegram:")
            and isinstance(item.get("approval_binding"), Mapping)
        )
        result.extend(
            (
                CapabilityEvidence(
                    "Human review delivery",
                    "LIVE_PROVEN" if review else "IMPLEMENTED",
                    review or ("implementation:runtime/tony_internal_review_delivery.py",),
                ),
                CapabilityEvidence(
                    "Conversational approval",
                    "LIVE_PROVEN" if approvals else "IMPLEMENTED",
                    approvals or ("implementation:runtime/tony_workflow_commands.py",),
                ),
                CapabilityEvidence(
                    "Full lifecycle recovery",
                    "IMPLEMENTED",
                    ("test:tests/test_production_os_lifecycle_acceptance.py",),
                    "Implementation and deterministic test exist; no broad live claim is inferred.",
                ),
            )
        )
        return tuple(result)

    @staticmethod
    def _recovery_proven(
        recovery: Mapping[str, Any],
        deployment: Mapping[str, Any],
        healthy_services: tuple[str, ...],
    ) -> bool:
        restarted = recovery.get("restarted_services")
        failed = recovery.get("failed_services")
        return (
            recovery.get("status") == "recovered"
            and isinstance(restarted, list)
            and bool(restarted)
            and isinstance(failed, list)
            and bool(failed)
            and int(recovery.get("exit_code_before") or 0) != 0
            and recovery.get("exit_code_after") == 0
            and recovery.get("deployment_healthy") is True
            and bool(healthy_services)
            and str(recovery.get("deployed_revision") or "")
            == str(deployment.get("deployed_revision") or "")
        )

    @staticmethod
    def _attention_proven(
        attention: Mapping[str, Any],
        deployment: Mapping[str, Any],
    ) -> bool:
        visible_ids = attention.get("visible_lead_ids")
        hidden_ids = attention.get("hidden_lead_ids")
        raw_count = attention.get("raw_lead_count")
        visible_count = attention.get("visible_lead_count")
        hidden_count = attention.get("hidden_lead_count")
        if (
            not isinstance(visible_ids, list)
            or not all(isinstance(item, str) for item in visible_ids)
            or not isinstance(hidden_ids, list)
            or not all(isinstance(item, str) for item in hidden_ids)
            or not isinstance(raw_count, int)
            or not isinstance(visible_count, int)
            or not isinstance(hidden_count, int)
        ):
            return False
        return (
            attention.get("status") == "accepted"
            and bool(hidden_ids)
            and not set(visible_ids).intersection(hidden_ids)
            and raw_count == visible_count + hidden_count
            and visible_count == len(visible_ids)
            and hidden_count == len(hidden_ids)
            and attention.get("morning_command_status") in {"healthy", "attention"}
            and attention.get("lead_command_status") == "healthy"
            and attention.get("duplicate_status") == "duplicate_suppressed"
            and attention.get("duplicate_attempts") == 0
            and attention.get("external_action_taken") is False
            and attention.get("client_workflow_mutations") == 0
            and str(attention.get("deployed_revision") or "")
            == str(deployment.get("deployed_revision") or "")
        )

    def _workflow_capability(
        self,
        states: tuple[WorkflowState, ...],
        workflow_id: str,
    ) -> CapabilityEvidence:
        matching = tuple(state for state in states if state.workflow_id == workflow_id)
        if not matching:
            return self._missing_workflow_capability(
                next(
                    name for name, candidate in self.WORKFLOW_CAPABILITIES if candidate == workflow_id
                ),
                workflow_id,
            )
        proven = tuple(
            state
            for state in matching
            if state.status.value in {"complete", "awaiting_approval"}
            and self._quality_passed(state)
        )
        capability = next(
            name for name, candidate in self.WORKFLOW_CAPABILITIES if candidate == workflow_id
        )
        if proven:
            return CapabilityEvidence(
                capability,
                "LIVE_PROVEN",
                tuple(self._run_evidence(state) for state in proven[-3:]),
            )
        failed = tuple(state for state in matching if state.status.value in {"blocked", "failed"})
        return CapabilityEvidence(
            capability,
            "FAILED" if failed else "IN_PROGRESS",
            tuple(f"workflow_run:{state.run_id}:{state.status.value}" for state in matching[-3:]),
        )

    def _missing_workflow_capability(self, capability: str, workflow_id: str) -> CapabilityEvidence:
        if workflow_id in self.workflow_ids:
            return CapabilityEvidence(
                capability,
                "IMPLEMENTED",
                (f"workflow_registry:{workflow_id}",),
            )
        return CapabilityEvidence(capability, "NOT_IMPLEMENTED", (), f"Missing workflow: {workflow_id}")

    @staticmethod
    def _additional_research_capability(states: tuple[WorkflowState, ...]) -> CapabilityEvidence:
        proven = tuple(
            state
            for state in states
            if "additional-research" in state.run_id
            and state.workflow_id == "growth_sprint_to_research_engine"
            and state.status.value == "complete"
            and AcceptanceProgrammeStatusBuilder._quality_passed(state)
        )
        return CapabilityEvidence(
            "Additional research",
            "LIVE_PROVEN" if proven else "IMPLEMENTED",
            tuple(AcceptanceProgrammeStatusBuilder._run_evidence(state) for state in proven[-3:])
            or ("implementation:runtime/tony_workflow_commands.py",),
        )

    @staticmethod
    def _telegram_evidence(
        states: tuple[WorkflowState, ...],
        conversations: tuple[dict[str, Any], ...],
    ) -> tuple[str, ...]:
        evidence = [
            f"conversation_work:{item.get('work_id')}"
            for item in conversations
            if item.get("state") == "completed" and item.get("external_action_taken") is True
        ]
        evidence.extend(
            f"telegram_approval:{state.run_id}"
            for state in states
            if any(
                str(item.get("approver") or "").startswith("telegram:")
                for item in state.approval_history
            )
        )
        return tuple(evidence[-3:])

    @staticmethod
    def _quality_passed(state: WorkflowState) -> bool:
        return any(
            isinstance(stage.quality_result, Mapping)
            and stage.quality_result.get("passed") is True
            and bool(stage.output_artifacts)
            for stage in state.stages
        )

    @staticmethod
    def _run_evidence(state: WorkflowState) -> str:
        artifact = next(
            (
                stage.output_artifacts[-1].artifact_id
                for stage in reversed(state.stages)
                if stage.output_artifacts
            ),
            "no-artifact",
        )
        return f"workflow_run:{state.run_id}:artifact:{artifact}"

    def _last_verified_checkpoint(self, states: tuple[WorkflowState, ...]) -> dict[str, Any] | None:
        by_workflow = {state.workflow_id: state for state in states}
        checkpoint: dict[str, Any] | None = None
        for capability, workflow_id in self.SCENARIO_SEQUENCE:
            state = by_workflow.get(workflow_id)
            if state is None or state.status.value != "complete" or not self._quality_passed(state):
                continue
            artifact = next(
                stage.output_artifacts[-1]
                for stage in reversed(state.stages)
                if stage.output_artifacts
            )
            checkpoint = {
                "capability": capability,
                "workflow_id": workflow_id,
                "run_id": state.run_id,
                "artifact_id": artifact.artifact_id,
                "artifact_checksum": artifact.checksum,
                "verified_at": state.updated_at,
            }
        return checkpoint

    @staticmethod
    def _failing_transition(states: tuple[WorkflowState, ...]) -> dict[str, Any] | None:
        failed = sorted(
            (state for state in states if state.status.value in {"blocked", "failed"}),
            key=lambda state: state.updated_at,
            reverse=True,
        )
        if not failed:
            return None
        state = failed[0]
        return {
            "workflow_id": state.workflow_id,
            "run_id": state.run_id,
            "status": state.status.value,
            "blocker": state.blocker,
        }
