from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.client_lifecycle import ClientLifecycleRecord
from runtime.campaign_world_triage_worker import CampaignWorldTriageWorker
from runtime.campaign_production_planning_worker import CampaignProductionPlanningWorker
from runtime.creative_bible_triage_worker import CreativeBibleTriageWorker
from runtime.creative_production_workflow_adapter import CreativeProductionWorkflowAdapter
from runtime.asset_delivery_preparation_worker import AssetDeliveryPreparationWorker
from runtime.client_asset_delivery_adapter import ClientAssetDeliveryAdapter
from runtime.delivery_follow_up_worker import DeliveryFollowUpPreparationWorker
from runtime.growth_blueprint_deliverable_worker import build_growth_blueprint_deliverable_worker
from runtime.models import StageStatus, WorkflowState, WorkflowStatus
from runtime.repositories import FileWorkflowRunRepository, JsonlEventLog
from runtime.research_workflow_adapter import ResearchWorkflowAdapter
from runtime.run_service import WorkflowRunService
from runtime.serialization import workflow_to_dict
from runtime.tony_blueprint_lite_inbound import TonyInboundBlueprintLiteService
from runtime.tony_dispatch_adapters import build_http_dispatchers
from runtime.worker_registry import WorkerAdapter, build_tony_worker_registry
from runtime.workflow_execution_coordinator import (
    ExecutionOutcome,
    FileWorkflowArtifactStore,
    QualityValidator,
    WorkflowExecutionCoordinator,
)
from runtime.workflow_business_projection import WorkflowBusinessProjectionService
from runtime.workflow_registry import build_narratiive_workflow_registry
from runtime.workflow_quality import (
    campaign_world_quality_gate,
    campaign_world_candidates_quality_gate,
    campaign_world_triage_quality_gate,
    creative_asset_production_quality_gate,
    delivery_preparation_quality_gate,
    client_asset_delivery_quality_gate,
    follow_up_preparation_quality_gate,
    creative_bible_quality_gate,
    creative_bible_triage_quality_gate,
    discovery_preparation_quality_gate,
    growth_blueprint_quality_gate,
    growth_blueprint_deliverable_quality_gate,
    growth_sprint_proposal_quality_gate,
    production_planning_quality_gate,
    research_evidence_quality_gate,
    validate_operational_inputs,
)
from runtime.workflow_handoffs import build_next_workflow_inputs
from runtime.workflow_run_identity import downstream_run_id


@dataclass(slots=True)
class TonyWorkflowRuntime:
    """Queryable application surface for one workspace/client execution scope."""

    coordinator: WorkflowExecutionCoordinator
    runs: WorkflowRunService
    business_projection: WorkflowBusinessProjectionService | None = None

    def enqueue(
        self,
        workflow_id: str,
        run_id: str,
        inputs: Mapping[str, Any],
        *,
        entity_id: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        validate_operational_inputs(workflow_id, inputs)
        state = self.coordinator.enqueue(
            workflow_id,
            run_id,
            inputs,
            entity_id=entity_id,
            correlation_id=correlation_id,
        )
        self._project(state)
        return workflow_to_dict(state)

    def advance(self, run_id: str, lifecycle: ClientLifecycleRecord) -> ExecutionOutcome:
        outcome = self.coordinator.advance(run_id, lifecycle)
        self._project(self.runs.load_run(run_id))
        return outcome

    def approve(
        self,
        run_id: str,
        *,
        approver: str,
        rationale: str,
        approval_binding: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        state = self.coordinator.approve(
            run_id,
            approver=approver,
            rationale=rationale,
            approval_binding=approval_binding,
        )
        self._project(state)
        return workflow_to_dict(state)

    def reject_for_revision(
        self,
        run_id: str,
        *,
        reviewer: str,
        rationale: str,
        approval_binding: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        current = self.runs.load_run(run_id)
        if current.status is WorkflowStatus.BLOCKED:
            state = self.runs.request_blocked_revision(
                run_id,
                reviewer=reviewer,
                rationale=rationale,
            )
        else:
            state = self.runs.reject_for_revision(
                run_id,
                reviewer=reviewer,
                rationale=rationale,
                approval_binding=approval_binding,
            )
        self._project(state)
        return workflow_to_dict(state)

    def resume(self, run_id: str) -> dict[str, Any]:
        state = self.runs.load_run(run_id)
        if state.status is not WorkflowStatus.BLOCKED or not state.current_stage_id:
            raise ValueError("workflow run is not blocked at a resumable step")
        stage = state.stage(state.current_stage_id)
        blocker = stage.blocker or state.blocker or ""
        if blocker.startswith("quality_failed:"):
            raise ValueError("quality failure requires an explicit revision request")
        if blocker == "ambiguous_external_action_requires_reconciliation":
            raise ValueError("external action must be reconciled before resume")
        if blocker.startswith("worker_unavailable:"):
            self.coordinator.workers.resolve(
                stage.capability,
                side_effect=stage.side_effect_classification,
            )
        if blocker.startswith("quality_validator_unavailable:") and stage.quality_contract not in self.coordinator.quality_validators:
            raise ValueError("declared quality validator is still unavailable")
        if stage.status is not StageStatus.BLOCKED:
            raise ValueError("workflow step is not resumable")
        state = self.runs.resume_stage(run_id, stage.stage_id, state.input_payload.keys())
        self._project(state)
        return workflow_to_dict(state)

    def status(self, run_id: str) -> dict[str, Any]:
        return workflow_to_dict(self.runs.load_run(run_id))

    def campaign_world_selection_brief(self, run_id: str) -> dict[str, Any]:
        state = self.runs.load_run(run_id)
        if state.workflow_id != "growth_blueprint_to_campaign_world":
            raise ValueError("run is not a Campaign World selection gate")
        candidates = state.input_payload.get("campaign_world_candidates")
        brief = state.input_payload.get("selection_brief")
        if not isinstance(candidates, list) or not isinstance(brief, Mapping):
            raise ValueError("Campaign World selection evidence is incomplete")
        ready = {str(item) for item in brief.get("ready_candidate_ids") or []}
        return {
            **dict(brief),
            "candidates": [
                {
                    "candidate_id": str(item.get("candidate_id") or ""),
                    "route_name": str(item.get("route_name") or ""),
                    "candidate_checksum": _workflow_value_checksum(item),
                    "ready_for_matt": str(item.get("candidate_id") or "") in ready,
                    "creative_north_star": dict(item.get("campaign_world", {}).get("creative_north_star", {}))
                    if isinstance(item, Mapping) and isinstance(item.get("campaign_world"), Mapping)
                    else {},
                }
                for item in candidates
                if isinstance(item, Mapping)
            ],
            "selection_recorded": any(
                item.get("decision") == "campaign_world_selection" for item in state.approval_history
            ),
        }

    def select_campaign_world(
        self,
        run_id: str,
        *,
        candidate_id: str,
        candidate_checksum: str,
        approver: str,
        rationale: str,
    ) -> dict[str, Any]:
        state = self.runs.load_run(run_id)
        brief = self.campaign_world_selection_brief(run_id)
        candidates = state.input_payload.get("campaign_world_candidates")
        selected = next(
            (item for item in candidates if isinstance(item, Mapping) and item.get("candidate_id") == candidate_id.strip()),
            None,
        ) if isinstance(candidates, list) else None
        if not isinstance(selected, Mapping):
            raise ValueError("unknown Campaign World candidate")
        if candidate_id.strip() not in set(brief.get("ready_candidate_ids") or []):
            raise ValueError("Matt may select only a candidate forwarded by Tony")
        expected = _workflow_value_checksum(selected)
        if not candidate_checksum.strip() or expected != candidate_checksum.strip():
            raise ValueError("Campaign World selection checksum is stale or incorrect")
        changed = self.runs.record_campaign_world_selection(
            run_id,
            approver=approver,
            rationale=rationale,
            candidate_id=candidate_id,
            candidate_checksum=expected,
        )
        self._project(changed)
        return workflow_to_dict(changed)

    def creative_bible_approval_brief(self, run_id: str) -> dict[str, Any]:
        state = self.runs.load_run(run_id)
        if state.workflow_id != "campaign_world_to_creative_bible":
            raise ValueError("run is not a Creative Bible approval gate")
        bible = state.input_payload.get("creative_directors_bible")
        brief = state.input_payload.get("creative_bible_approval_brief")
        review = state.input_payload.get("creative_bible_review")
        if not isinstance(bible, Mapping) or not isinstance(brief, Mapping) or not isinstance(review, Mapping):
            raise ValueError("Creative Bible approval evidence is incomplete")
        checksum = _workflow_value_checksum(bible)
        if checksum != brief.get("creative_bible_checksum") or checksum != review.get("reviewed_bible_checksum"):
            raise ValueError("Creative Bible review no longer matches the exact Bible version")
        north_star = bible.get("creative_north_star")
        return {
            **dict(brief),
            "creative_bible_checksum": checksum,
            "creative_north_star": dict(north_star) if isinstance(north_star, Mapping) else {},
            "tony_review": dict(review),
            "approval_recorded": any(
                item.get("decision") == "creative_bible_approval" for item in state.approval_history
            ),
        }

    def approve_creative_bible(
        self,
        run_id: str,
        *,
        creative_bible_checksum: str,
        approver: str,
        rationale: str,
    ) -> dict[str, Any]:
        brief = self.creative_bible_approval_brief(run_id)
        expected = str(brief.get("creative_bible_checksum") or "")
        if not creative_bible_checksum.strip() or creative_bible_checksum.strip() != expected:
            raise ValueError("Creative Bible approval checksum is stale or incorrect")
        if brief.get("requires_matt") is not True or brief.get("tony_disposition") != "forward":
            raise ValueError("Creative Bible has not been forwarded by Tony for Matt approval")
        changed = self.runs.record_creative_bible_approval(
            run_id,
            approver=approver,
            rationale=rationale,
            creative_bible_checksum=expected,
        )
        self._project(changed)
        return workflow_to_dict(changed)

    def asset_suite_approval_brief(self, run_id: str) -> dict[str, Any]:
        state = self.runs.load_run(run_id)
        if state.workflow_id != "creative_bible_to_asset_production":
            raise ValueError("run is not an asset-suite approval gate")
        versions = state.input_payload.get("asset_versions")
        if not isinstance(versions, list) or not versions or not all(isinstance(item, Mapping) for item in versions):
            raise ValueError("asset-suite approval evidence is incomplete")
        required = ("asset_version_id", "asset_id", "file_checksum", "drive_uri", "production_job_id")
        if any(any(not str(item.get(field) or "").strip() for field in required) for item in versions):
            raise ValueError("asset-suite contains an incomplete generated version")
        if any(item.get("human_review_required") is not True for item in versions):
            raise ValueError("asset-suite version does not require human review")
        checksum = _workflow_value_checksum(versions)
        return {
            "asset_suite_checksum": checksum,
            "asset_count": len(versions),
            "asset_versions": [
                {
                    "asset_version_id": str(item["asset_version_id"]),
                    "asset_id": str(item["asset_id"]),
                    "file_checksum": str(item["file_checksum"]),
                    "drive_uri": str(item["drive_uri"]),
                    "status": str(item.get("status") or ""),
                    "approval_status": str(item.get("approval_status") or "pending"),
                }
                for item in versions
            ],
            "requires_matt": True,
            "auto_approval_authorised": False,
            "delivery_authorised": False,
            "publication_authorised": False,
            "media_spend_authorised": False,
            "approval_recorded": any(
                item.get("decision") == "asset_suite_approval" for item in state.approval_history
            ),
        }

    def approve_asset_suite(
        self,
        run_id: str,
        *,
        asset_suite_checksum: str,
        approver: str,
        rationale: str,
    ) -> dict[str, Any]:
        state = self.runs.load_run(run_id)
        brief = self.asset_suite_approval_brief(run_id)
        expected = str(brief["asset_suite_checksum"])
        if not asset_suite_checksum.strip() or asset_suite_checksum.strip() != expected:
            raise ValueError("asset-suite approval checksum is stale or incorrect")
        versions = state.input_payload.get("asset_versions")
        changed = self.runs.record_asset_suite_approval(
            run_id,
            approver=approver,
            rationale=rationale,
            asset_suite_checksum=expected,
            asset_version_ids=[str(item["asset_version_id"]) for item in versions],
        )
        self._project(changed)
        return workflow_to_dict(changed)

    def handoff(
        self,
        run_id: str,
        lifecycle: ClientLifecycleRecord,
        additional_inputs: Mapping[str, Any] | None = None,
    ) -> ExecutionOutcome:
        state = self.runs.load_run(run_id)
        definition = self.coordinator.registry.resolve(state.workflow_id)
        if state.status is not WorkflowStatus.COMPLETE:
            raise ValueError("workflow must be complete before handoff")
        if state.approval_required and state.approval_status != "approved":
            raise ValueError("workflow handoff requires explicit approval")
        if not definition.next_workflow_id:
            raise ValueError("workflow has no registered next workflow")
        artifacts = [artifact for stage in state.stages for artifact in stage.output_artifacts]
        if not artifacts:
            raise ValueError("workflow handoff requires a persisted artefact")
        output = self.coordinator.artifacts.root.joinpath(Path(artifacts[-1].location).name)
        try:
            value = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("workflow handoff artefact is unreadable") from exc
        if not isinstance(value, Mapping):
            raise ValueError("workflow handoff artefact must be structured")
        inputs = build_next_workflow_inputs(state, value, additional_inputs)
        next_definition = self.coordinator.registry.resolve(definition.next_workflow_id)
        next_stage = next_definition.stages[0]
        if definition.next_workflow_id == "growth_blueprint_deliverable_production":
            source_artifact = artifacts[-1]
            if not source_artifact.checksum:
                raise ValueError("approved Blueprint artefact is missing its immutable checksum")
            inputs["quality_accepted_growth_blueprint"] = dict(value)
            inputs["blueprint_identity"] = {
                "artifact_id": source_artifact.artifact_id,
                "version": 1,
                "checksum": source_artifact.checksum,
            }
            inputs["blueprint_canon"] = {
                "artifact_id": source_artifact.artifact_id,
                "checksum": source_artifact.checksum,
                "status": "quality_accepted_and_human_approved",
            }
        if state.workflow_id == "growth_blueprint_to_campaign_world":
            selection = next(
                (
                    item for item in reversed(state.approval_history)
                    if item.get("decision") == "campaign_world_selection"
                ),
                None,
            )
            if not isinstance(selection, Mapping):
                raise ValueError("Campaign World handoff requires Matt's exact candidate selection")
            candidates = state.input_payload.get("campaign_world_candidates")
            selected = next(
                (
                    item for item in candidates
                    if isinstance(item, Mapping) and item.get("candidate_id") == selection.get("candidate_id")
                ),
                None,
            ) if isinstance(candidates, list) else None
            if not isinstance(selected, Mapping) or _workflow_value_checksum(selected) != selection.get("candidate_checksum"):
                raise ValueError("recorded Campaign World selection no longer matches candidate evidence")
            inputs["approved_campaign_world"] = dict(selected["campaign_world"])
            inputs["campaign_world_selection"] = dict(selection)
        if state.workflow_id == "campaign_world_to_creative_bible":
            approval = next(
                (
                    item for item in reversed(state.approval_history)
                    if item.get("decision") == "creative_bible_approval"
                ),
                None,
            )
            bible = state.input_payload.get("creative_directors_bible")
            if not isinstance(approval, Mapping):
                raise ValueError("Creative Bible handoff requires Matt's exact-version approval")
            if not isinstance(bible, Mapping) or _workflow_value_checksum(bible) != approval.get("creative_bible_checksum"):
                raise ValueError("recorded Creative Bible approval no longer matches the Bible evidence")
            inputs["approved_creative_bible"] = dict(bible)
            inputs["creative_bible_approval"] = dict(approval)
        if state.workflow_id == "creative_bible_to_asset_production":
            approval = next(
                (
                    item for item in reversed(state.approval_history)
                    if item.get("decision") == "asset_suite_approval"
                ),
                None,
            )
            versions = state.input_payload.get("asset_versions")
            if not isinstance(approval, Mapping):
                raise ValueError("delivery handoff requires Matt's exact asset-suite approval")
            if not isinstance(versions, list) or _workflow_value_checksum(versions) != approval.get("asset_suite_checksum"):
                raise ValueError("recorded asset-suite approval no longer matches generated asset evidence")
            inputs["reviewed_assets"] = [
                {
                    **dict(item),
                    "status": "approved",
                    "approval_status": "approved",
                    "source_asset_suite_checksum": approval["asset_suite_checksum"],
                }
                for item in versions
                if isinstance(item, Mapping)
            ]
            inputs["asset_suite_approval"] = dict(approval)
        for field in next_stage.output_contract.required_fields:
            if field not in next_stage.input_contract.required_fields:
                inputs.pop(field, None)
        missing = [field for field in next_stage.input_contract.required_fields if field not in inputs or inputs[field] in (None, "", [], {})]
        if missing:
            raise ValueError(f"next workflow requires additional inputs: {','.join(missing)}")
        next_run_id = downstream_run_id(state.run_id, definition.next_workflow_id)
        self.enqueue(
            definition.next_workflow_id,
            next_run_id,
            inputs,
            entity_id=state.entity_id,
            correlation_id=state.correlation_id,
        )
        self.runs.record_handoff(
            run_id,
            next_workflow_id=definition.next_workflow_id,
            next_run_id=next_run_id,
        )
        self._project(self.runs.load_run(run_id))
        return self.advance(next_run_id, lifecycle)

    def commission(
        self,
        source_run_id: str,
        target_workflow_id: str,
        additional_inputs: Mapping[str, Any],
        *,
        commitment_id: str,
    ) -> tuple[WorkflowState, bool]:
        """Persist authorised future work before Tony says it is underway.

        Execution is deliberately left to the restart-safe promised-work worker.
        The target must be downstream of the source in the registered workflow
        chain, so this cannot manufacture an unrelated work item.
        """

        source = self.runs.load_run(source_run_id)
        if source.status is not WorkflowStatus.COMPLETE:
            raise ValueError("source workflow must be complete before commissioning downstream work")
        if source.approval_required and source.approval_status != "approved":
            raise ValueError("source workflow requires explicit approval before commissioning downstream work")
        target_id = target_workflow_id.strip()
        definition = self.coordinator.registry.resolve(source.workflow_id)
        reachable: set[str] = set()
        cursor = definition.next_workflow_id
        while cursor and cursor not in reachable:
            reachable.add(cursor)
            cursor = self.coordinator.registry.resolve(cursor).next_workflow_id
        if target_id not in reachable:
            raise ValueError("commissioned workflow must be downstream of the source workflow")

        artifacts = [artifact for stage in source.stages for artifact in stage.output_artifacts]
        if not artifacts:
            raise ValueError("workflow commission requires a persisted source artefact")
        try:
            source_output = json.loads(Path(artifacts[-1].location).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("workflow commission source artefact is unreadable") from exc
        if not isinstance(source_output, Mapping):
            raise ValueError("workflow commission source artefact must be structured")

        target = self.coordinator.registry.resolve(target_id)
        required = target.stages[0].input_contract.required_fields
        supplied = {**dict(source_output), **dict(additional_inputs)}
        supplied["_lineage"] = {
            "parent_workflow_id": source.workflow_id,
            "parent_run_id": source.run_id,
            "parent_artifact_ids": [artifact.artifact_id for artifact in artifacts],
            "recovered_intermediate_evidence": target_id != definition.next_workflow_id,
        }
        supplied["_promised_work"] = {
            "commitment_id": commitment_id.strip(),
            "source_run_id": source.run_id,
            "delivery_channel": "telegram",
            "state": "commissioned",
        }
        if "commercial_context" in required and not isinstance(supplied.get("commercial_context"), Mapping):
            supplied["commercial_context"] = {
                "company": str(source.input_payload.get("company") or source.input_payload.get("company_name") or "").strip(),
                "source_ref": f"workflow_run:{source.run_id}",
            }
        missing = [field for field in required if field not in supplied or supplied[field] in (None, "", [], {})]
        if missing:
            raise ValueError(f"commissioned workflow requires additional inputs: {','.join(missing)}")

        next_run_id = downstream_run_id(source.run_id, target_id)
        replay = self.runs.repository.exists(next_run_id)
        if replay:
            existing = self.runs.load_run(next_run_id)
            existing_commitment = existing.input_payload.get("_promised_work", {})
            if not isinstance(existing_commitment, Mapping) or existing_commitment.get("commitment_id") != commitment_id.strip():
                raise ValueError("a different durable work item already exists for this workflow transition")
            return existing, True
        self.enqueue(
            target_id,
            next_run_id,
            supplied,
            entity_id=source.entity_id,
            correlation_id=source.correlation_id,
        )
        commissioned = self.runs.record_commission(
            next_run_id,
            source_run_id=source.run_id,
            target_workflow_id=target_id,
            commitment_id=commitment_id,
        )
        return commissioned, False

    def list_run_ids(self) -> list[str]:
        return self.runs.repository.list_run_ids()

    def recover_pending(self) -> int:
        recovered = self.coordinator.recover_pending()
        for run_id in self.list_run_ids():
            self._project(self.runs.load_run(run_id))
        return recovered

    def sync_business_projection(self, run_id: str, *, approver: str, rationale: str) -> dict[str, Any]:
        if self.business_projection is None:
            raise ValueError("business projection is not configured")
        return self.business_projection.sync(
            self.runs.load_run(run_id),
            approver=approver,
            rationale=rationale,
        )

    def _project(self, state: WorkflowState) -> None:
        if self.business_projection is not None:
            self.business_projection.prepare(state)


def build_tony_workflow_runtime(
    root: str | Path,
    *,
    workspace_id: str,
    client_id: str,
    dispatchers: Mapping[str, WorkerAdapter] | None = None,
    environ: Mapping[str, str] | None = None,
    quality_validators: Mapping[str, QualityValidator] | None = None,
) -> TonyWorkflowRuntime:
    """Compose the production workflow runtime without executing any work."""

    scope = hashlib.sha256(f"{workspace_id}:{client_id}".encode("utf-8")).hexdigest()[:24]
    scoped_root = Path(root) / scope
    repository = FileWorkflowRunRepository(
        scoped_root / "runs",
        workspace_id=workspace_id,
        client_id=client_id,
    )
    events = JsonlEventLog(scoped_root / "events", workspace_id=workspace_id)
    runs = WorkflowRunService(
        repository,
        events,
        workspace_id=workspace_id,
        client_id=client_id,
    )
    configured_dispatchers = dict(dispatchers) if dispatchers is not None else build_http_dispatchers(environ)
    document_adapter = build_growth_blueprint_deliverable_worker(scoped_root, environ)
    validators: dict[str, QualityValidator] = {
        "blueprint_lite_quality_gate": TonyInboundBlueprintLiteService._quality_gate,
        "discovery_preparation_quality_gate": discovery_preparation_quality_gate,
        "growth_sprint_proposal_quality_gate": growth_sprint_proposal_quality_gate,
        "research_evidence_quality_gate": research_evidence_quality_gate,
        "growth_blueprint_quality_gate": growth_blueprint_quality_gate,
        "growth_blueprint_deliverable_quality_gate": growth_blueprint_deliverable_quality_gate,
        "campaign_world_quality_gate": campaign_world_quality_gate,
        "campaign_world_candidates_quality_gate": campaign_world_candidates_quality_gate,
        "campaign_world_triage_quality_gate": campaign_world_triage_quality_gate,
        "production_planning_quality_gate": production_planning_quality_gate,
        "creative_asset_production_quality_gate": creative_asset_production_quality_gate,
        "delivery_preparation_quality_gate": delivery_preparation_quality_gate,
        "client_asset_delivery_quality_gate": client_asset_delivery_quality_gate,
        "follow_up_preparation_quality_gate": follow_up_preparation_quality_gate,
        "creative_bible_quality_gate": creative_bible_quality_gate,
        "creative_bible_triage_quality_gate": creative_bible_triage_quality_gate,
    }
    validators.update(dict(quality_validators or {}))
    coordinator = WorkflowExecutionCoordinator(
        registry=build_narratiive_workflow_registry(),
        workers=build_tony_worker_registry(
            configured_dispatchers,
            environ,
            research_adapter=ResearchWorkflowAdapter(
                scoped_root,
                fireflies_dispatcher=configured_dispatchers.get("Fireflies"),
            ),
            document_adapter=document_adapter,
            campaign_world_triage_adapter=CampaignWorldTriageWorker(),
            creative_bible_triage_adapter=CreativeBibleTriageWorker(),
            production_planning_adapter=CampaignProductionPlanningWorker(),
            creative_production_adapter=(
                CreativeProductionWorkflowAdapter(configured_dispatchers["Creative Production"])
                if "Creative Production" in configured_dispatchers
                else None
            ),
            delivery_preparation_adapter=AssetDeliveryPreparationWorker(),
            client_delivery_adapter=(
                ClientAssetDeliveryAdapter(configured_dispatchers["Client Delivery"])
                if "Client Delivery" in configured_dispatchers
                else None
            ),
            follow_up_planning_adapter=DeliveryFollowUpPreparationWorker(),
        ),
        runs=runs,
        artifacts=FileWorkflowArtifactStore(scoped_root / "artifacts"),
        quality_validators=validators,
    )
    projection = WorkflowBusinessProjectionService(
        scoped_root / "business-projection",
        dispatcher=configured_dispatchers.get("Notion"),
    )
    return TonyWorkflowRuntime(coordinator=coordinator, runs=runs, business_projection=projection)


def _workflow_value_checksum(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
