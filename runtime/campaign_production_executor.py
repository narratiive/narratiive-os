from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from runtime.campaign_engine import (
    CampaignEngine,
    CampaignEngineApplicationService,
    CampaignEngineError,
    CampaignEngineStage,
    CampaignEngineState,
    ProducedAssetVersion,
)
from runtime.execution_journal import ExecutionJournal
from runtime.worker_registry import (
    CapabilityWorkerRegistry,
    NoAvailableWorker,
    WorkerAvailability,
    WorkerResolution,
)


class ProductionExecutionError(RuntimeError):
    """Raised when an approved production dispatch cannot be trusted."""


class ProductionExecutionRecoveryRequired(ProductionExecutionError):
    """Raised when a prior attempt may have produced an unrecorded external result."""


class CampaignProductionExecutor:
    """Execute one exactly approved production payload and persist its Drive receipt."""

    def __init__(
        self,
        *,
        registry: CapabilityWorkerRegistry,
        application: CampaignEngineApplicationService,
        journal: ExecutionJournal,
    ) -> None:
        self.registry = registry
        self.application = application
        self.journal = journal

    def execute(
        self,
        expected: CampaignEngineState,
        *,
        dispatch_id: str,
        transition_id: str,
    ) -> tuple[CampaignEngineState, bool]:
        context = self._context(expected, dispatch_id)
        decision_id = self._decision_id(expected, dispatch_id)
        latest = self.journal.latest(decision_id)
        if latest is not None:
            if latest.status == "completed":
                return self._recover_completed(expected, latest.metadata, transition_id), True
            raise ProductionExecutionRecoveryRequired(
                f"production dispatch {dispatch_id} has a prior {latest.status} attempt; reconcile the provider and Drive receipt before retry"
            )
        if any(version.production_job_id == context["job"].job_id for version in expected.asset_versions):
            raise ProductionExecutionError(
                "campaign state contains a produced asset without matching execution-journal evidence"
            )

        resolution = self._resolution(context["preview"])
        self.journal.append(
            decision_id=decision_id,
            workspace_id=expected.identity.workspace_id,
            client_id=expected.identity.client_id,
            action="execute-approved-production-dispatch",
            rationale="Matt approved the exact production payload checksum.",
            actor=resolution.worker_id,
            status="dispatched",
            record_id=f"{decision_id}:dispatched",
            metadata=self._journal_context(expected, context),
        )
        try:
            result = self.registry.execute(
                resolution,
                {
                    "execution_mode": "approved_production",
                    "idempotency_key": decision_id,
                    "dispatch_id": dispatch_id,
                    "payload_checksum": context["preview"].payload_checksum,
                    "approved_payload": json.loads(context["preview"].payload_json),
                    "approval": {
                        "approver": context["approval"].approver,
                        "rationale": context["approval"].rationale,
                    },
                },
                side_effect="external_write",
                approval_granted=True,
            )
            version = self._version_from_result(expected, context, result)
            proposed = CampaignEngine().register_asset_version(expected, version)
            self.journal.append(
                decision_id=decision_id,
                workspace_id=expected.identity.workspace_id,
                client_id=expected.identity.client_id,
                action="execute-approved-production-dispatch",
                rationale="Provider output was verified and bound to a Drive asset version.",
                actor=resolution.worker_id,
                status="completed",
                record_id=f"{decision_id}:completed",
                artifacts=(version.drive_uri,),
                metadata={
                    **self._journal_context(expected, context),
                    "asset_version": self._version_dict(version),
                    "provider_receipt_id": str(result.get("provider_receipt_id") or ""),
                },
            )
            persisted = self.application.persist_transition(
                expected,
                proposed,
                transition_id=transition_id,
            )
            return persisted, False
        except Exception as exc:
            if self.journal.latest(decision_id).status != "completed":
                self.journal.append(
                    decision_id=decision_id,
                    workspace_id=expected.identity.workspace_id,
                    client_id=expected.identity.client_id,
                    action="execute-approved-production-dispatch",
                    rationale="Production execution failed closed and requires operator inspection.",
                    actor=resolution.worker_id,
                    status="failed",
                    record_id=f"{decision_id}:failed",
                    metadata={
                        **self._journal_context(expected, context),
                        "error_type": type(exc).__name__,
                    },
                )
            raise

    def _context(self, state: CampaignEngineState, dispatch_id: str) -> dict[str, Any]:
        if state.stage is not CampaignEngineStage.ASSET_PRODUCTION:
            raise CampaignEngineError("production execution requires the asset-production stage")
        if state.production_plan is None or state.asset_manifest is None:
            raise CampaignEngineError("production execution requires a Production Plan and Asset Manifest")
        preview = next(
            (item for item in state.production_dispatch_previews if item.dispatch_id == dispatch_id),
            None,
        )
        if preview is None:
            raise CampaignEngineError("production execution references an unknown dispatch preview")
        approval = next(
            (item for item in state.production_dispatch_approvals if item.dispatch_id == dispatch_id),
            None,
        )
        if approval is None or approval.payload_checksum != preview.payload_checksum:
            raise CampaignEngineError("production execution requires Matt's exact-payload approval")
        route = next(item for item in state.production_routes if item.route_id == preview.route_id)
        job = next(item for item in state.production_plan.jobs if item.job_id == preview.job_id)
        asset = next(
            item for item in state.asset_manifest.assets if item.production_job_id == job.job_id
        )
        return {
            "preview": preview,
            "approval": approval,
            "route": route,
            "job": job,
            "asset": asset,
        }

    def _resolution(self, preview: Any) -> WorkerResolution:
        registration = next(
            (item for item in self.registry.all() if item.metadata.worker_id == preview.worker_id),
            None,
        )
        if registration is None:
            raise NoAvailableWorker(f"approved production worker is not registered: {preview.worker_id}")
        metadata = registration.metadata
        if metadata.availability not in {WorkerAvailability.AVAILABLE, WorkerAvailability.DEGRADED}:
            raise NoAvailableWorker(f"approved production worker is unavailable: {preview.worker_id}")
        if registration.adapter is None:
            raise NoAvailableWorker(f"approved production worker has no adapter: {preview.worker_id}")
        if preview.required_capability not in metadata.capabilities:
            raise NoAvailableWorker("approved production worker no longer provides the required capability")
        if "external_write" not in metadata.side_effect_permissions:
            raise NoAvailableWorker("approved production worker is not configured for production execution")
        if metadata.provider != preview.provider:
            raise NoAvailableWorker("approved production provider no longer matches the planned route")
        return WorkerResolution(
            registration=registration,
            capability=preview.required_capability,
            policy_id="exact-approved-production-route",
            reason="bound_to_approved_dispatch_preview",
        )

    @staticmethod
    def _version_from_result(
        state: CampaignEngineState,
        context: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> ProducedAssetVersion:
        if result.get("verified") is not True or result.get("external_action_taken") is not True:
            raise ProductionExecutionError("production worker did not return verified execution evidence")
        authority_fields = ("publication_authorised", "media_spend_authorised", "delivery_authorised")
        if any(result.get(field) is not False for field in authority_fields):
            raise ProductionExecutionError(
                "production worker must explicitly deny publication, delivery and media-spend authority"
            )
        if not str(result.get("provider_receipt_id") or "").strip():
            raise ProductionExecutionError("production worker did not return a provider receipt")
        asset = result.get("asset_version")
        if not isinstance(asset, Mapping):
            raise ProductionExecutionError("production worker did not return a structured asset_version")
        planned = context["asset"]
        job = context["job"]
        existing = [item.version_number for item in state.asset_versions if item.asset_id == planned.asset_id]
        expected_version = max(existing, default=0) + 1
        try:
            version = ProducedAssetVersion(
                asset_version_id=str(asset.get("asset_version_id") or "").strip(),
                asset_id=str(asset.get("asset_id") or "").strip(),
                version_number=int(asset.get("version_number")),
                file_checksum=str(asset.get("file_checksum") or "").strip(),
                drive_uri=str(asset.get("drive_uri") or "").strip(),
                producer=str(asset.get("producer") or "").strip(),
                production_job_id=str(asset.get("production_job_id") or "").strip(),
                source_manifest_checksum=str(asset.get("source_manifest_checksum") or "").strip(),
            )
        except (TypeError, ValueError) as exc:
            raise ProductionExecutionError("production worker returned a malformed asset version") from exc
        if version.asset_id != planned.asset_id or version.production_job_id != job.job_id:
            raise ProductionExecutionError("production worker output does not match the planned asset and job")
        if version.source_manifest_checksum != state.asset_manifest.manifest_artifact.checksum:
            raise ProductionExecutionError("production worker output does not match the Asset Manifest")
        if version.version_number != expected_version:
            raise ProductionExecutionError("production worker output is not the next append-only asset version")
        return version

    def _recover_completed(
        self,
        expected: CampaignEngineState,
        metadata: Mapping[str, Any],
        transition_id: str,
    ) -> CampaignEngineState:
        raw = metadata.get("asset_version")
        if not isinstance(raw, Mapping):
            raise ProductionExecutionRecoveryRequired("completed production receipt has no asset version evidence")
        version = ProducedAssetVersion(
            asset_version_id=str(raw.get("asset_version_id") or ""),
            asset_id=str(raw.get("asset_id") or ""),
            version_number=int(raw.get("version_number")),
            file_checksum=str(raw.get("file_checksum") or ""),
            drive_uri=str(raw.get("drive_uri") or ""),
            producer=str(raw.get("producer") or ""),
            production_job_id=str(raw.get("production_job_id") or ""),
            source_manifest_checksum=str(raw.get("source_manifest_checksum") or ""),
        )
        existing = next(
            (item for item in expected.asset_versions if item.asset_version_id == version.asset_version_id),
            None,
        )
        if existing is not None:
            if existing != version:
                raise ProductionExecutionRecoveryRequired("persisted asset conflicts with completed production receipt")
            return expected
        proposed = CampaignEngine().register_asset_version(expected, version)
        return self.application.persist_transition(expected, proposed, transition_id=transition_id)

    @staticmethod
    def _decision_id(state: CampaignEngineState, dispatch_id: str) -> str:
        return (
            f"production:{state.identity.workspace_id}:{state.identity.client_id}:"
            f"{state.identity.campaign_id}:{dispatch_id}"
        )

    @staticmethod
    def _journal_context(state: CampaignEngineState, context: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "campaign_id": state.identity.campaign_id,
            "dispatch_id": context["preview"].dispatch_id,
            "payload_checksum": context["preview"].payload_checksum,
            "job_id": context["job"].job_id,
            "asset_id": context["asset"].asset_id,
            "worker_id": context["preview"].worker_id,
            "provider": context["preview"].provider,
            "publication_authorised": False,
            "media_spend_authorised": False,
        }

    @staticmethod
    def _version_dict(version: ProducedAssetVersion) -> dict[str, Any]:
        return {
            "asset_version_id": version.asset_version_id,
            "asset_id": version.asset_id,
            "version_number": version.version_number,
            "file_checksum": version.file_checksum,
            "drive_uri": version.drive_uri,
            "producer": version.producer,
            "production_job_id": version.production_job_id,
            "source_manifest_checksum": version.source_manifest_checksum,
        }
