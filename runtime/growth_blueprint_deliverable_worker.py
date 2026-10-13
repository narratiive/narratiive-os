from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.deliverable_production import (
    DeliverableProductionRecord,
    DeliverableProductionService,
    FileDeliverableStore,
    LocalArtifactToolPresentationRenderer,
    PresentationSpecification,
    _checksum,
    augment_specification_with_commercial_evidence,
    bind_source_register_to_specification,
    build_growth_blueprint_presentation_spec,
    build_quantified_commercial_model,
    commercial_model_quality_checks,
)

WorkerAdapter = Callable[[dict[str, Any]], dict[str, Any]]


class GrowthBlueprintDeliverableWorkerError(RuntimeError):
    """Raised when a Blueprint deliverable cannot be produced truthfully."""


RENDERER_CONTRACT_VERSION = "growth-blueprint-renderer-v10"


class GrowthBlueprintDeliverableWorker:
    """Render a canonical Blueprint draft for internal human review only."""

    def __init__(
        self,
        *,
        renderer: LocalArtifactToolPresentationRenderer,
        store: FileDeliverableStore,
        output_root: Path,
    ) -> None:
        self.renderer = renderer
        self.store = store
        self.output_root = Path(output_root)

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        context = contract.get("workflow_context")
        if not isinstance(context, Mapping):
            raise GrowthBlueprintDeliverableWorkerError("document worker requires workflow context")
        if context.get("workflow_id") != "growth_blueprint_deliverable_production":
            raise GrowthBlueprintDeliverableWorkerError("document worker received an unsupported workflow")
        blueprint = contract.get("quality_accepted_growth_blueprint")
        identity = contract.get("blueprint_identity")
        client_context = contract.get("client_context")
        commercial_intelligence = contract.get("commercial_intelligence")
        source_register = contract.get("source_register")
        if not isinstance(blueprint, Mapping) or not isinstance(identity, Mapping):
            raise GrowthBlueprintDeliverableWorkerError("document worker requires structured Blueprint evidence")
        if not isinstance(client_context, Mapping):
            raise GrowthBlueprintDeliverableWorkerError("document worker requires structured client context")
        if not isinstance(commercial_intelligence, Mapping) or not isinstance(source_register, Mapping):
            raise GrowthBlueprintDeliverableWorkerError(
                "full Blueprint production requires commercial intelligence and a source register"
            )

        workspace_id = str(context.get("workspace_id") or "").strip()
        client_id = str(context.get("client_id") or "").strip()
        run_id = str(context.get("run_id") or "").strip()
        source_id = str(identity.get("artifact_id") or "").strip()
        source_checksum = str(identity.get("checksum") or "").strip()
        brand_name = str(
            client_context.get("brand_name")
            or client_context.get("company_name")
            or client_context.get("company")
            or client_context.get("name")
            or ""
        ).strip()
        try:
            source_version = int(identity.get("version"))
        except (TypeError, ValueError) as exc:
            raise GrowthBlueprintDeliverableWorkerError("Blueprint identity has an invalid version") from exc
        if not all((workspace_id, client_id, run_id, source_id, source_checksum, brand_name)):
            raise GrowthBlueprintDeliverableWorkerError("document worker identity is incomplete")
        if source_checksum != _checksum(blueprint):
            raise GrowthBlueprintDeliverableWorkerError("Blueprint identity checksum does not match the supplied source")

        stable_id = hashlib.sha256(
            f"{RENDERER_CONTRACT_VERSION}:{workspace_id}:{client_id}:{run_id}:{source_id}:{source_checksum}".encode("utf-8")
        ).hexdigest()[:20]
        specification = build_growth_blueprint_presentation_spec(
            blueprint,
            specification_id=f"blueprint-spec-{stable_id}",
            source_blueprint_id=source_id,
            source_blueprint_version=source_version,
            workspace_id=workspace_id,
            client_id=client_id,
            title=f"Narratiive Growth Blueprint — {brand_name}",
            brand_name=brand_name,
        )
        try:
            commercial_model = build_quantified_commercial_model(commercial_intelligence)
            model_checks = commercial_model_quality_checks(commercial_model)
            if not all(model_checks.values()):
                raise ValueError(f"commercial model quality failed: {model_checks}")
            specification = augment_specification_with_commercial_evidence(
                specification,
                commercial_model=commercial_model,
                source_register=source_register,
                production_direction=commercial_intelligence.get("production_direction") or {},
            )
            specification, source_register = bind_source_register_to_specification(
                specification, source_register
            )
        except ValueError as exc:
            raise GrowthBlueprintDeliverableWorkerError(str(exc)) from exc
        deliverable_id = f"growth-blueprint-{stable_id}"
        existing = self.store.load(workspace_id, client_id, deliverable_id)
        if existing is not None:
            self._validate_existing(existing, specification)
            return self._output(
                existing, specification, commercial_model=commercial_model,
                source_register=source_register, replay=True,
                elapsed_seconds=time.perf_counter() - started,
            )

        output_dir = self.output_root / workspace_id / client_id / deliverable_id
        record = DeliverableProductionService(self.renderer, self.store).produce(
            blueprint,
            specification=specification,
            deliverable_id=deliverable_id,
            output_dir=output_dir,
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        return self._output(
            record, specification, commercial_model=commercial_model,
            source_register=source_register, replay=False,
            elapsed_seconds=time.perf_counter() - started,
        )

    @staticmethod
    def _validate_existing(
        record: DeliverableProductionRecord,
        specification: PresentationSpecification,
    ) -> None:
        if (
            record.source_blueprint_id != specification.source_blueprint_id
            or record.source_blueprint_version != specification.source_blueprint_version
            or record.specification_checksum != _checksum(specification.to_dict())
        ):
            raise GrowthBlueprintDeliverableWorkerError("existing deliverable conflicts with Blueprint lineage")
        if not record.visual_qa.passed or not Path(record.pptx_path).is_file() or not Path(record.pdf_path).is_file():
            raise GrowthBlueprintDeliverableWorkerError("existing deliverable does not have verified files and visual QA")

    @staticmethod
    def _output(
        record: DeliverableProductionRecord,
        specification: PresentationSpecification,
        *,
        commercial_model: Mapping[str, Any],
        source_register: Mapping[str, Any],
        replay: bool,
        elapsed_seconds: float,
    ) -> dict[str, Any]:
        return {
            "presentation_specification": specification.to_dict(),
            "commercial_model": dict(commercial_model),
            "source_register": dict(source_register),
            "editable_pptx": record.pptx_path,
            "review_pdf": record.pdf_path,
            "visual_qa": record.visual_qa.to_dict(),
            "execution_evidence": {
                "executor": "tony-local-artifact-tool",
                "codex_dependency": False,
                "elapsed_seconds": round(elapsed_seconds, 3),
                "provider_calls": 0,
                "estimated_provider_cost_gbp": 0.0,
                "cost_basis": "Deterministic local modelling, rendering, PDF assembly and rendered-slide review; excludes local compute and sunk upstream research/generation cost.",
            },
            "proposed_client_release": {
                "status": "pending_human_approval",
                "deliverable_id": record.deliverable_id,
                "approval_required": True,
            },
            "approval_status": "pending",
            "external_action_taken": False,
            "publication_authorised": False,
            "delivery_authorised": False,
            "replay": replay,
        }


def build_growth_blueprint_deliverable_worker(
    root: str | Path,
    environ: Mapping[str, str] | None = None,
) -> WorkerAdapter | None:
    env = os.environ if environ is None else environ
    mode = str(env.get("NARRATIIVE_DOCUMENT_WORKER_MODE") or "").strip().casefold()
    if not mode:
        return None
    if mode != "local_artifact_tool":
        raise GrowthBlueprintDeliverableWorkerError("unsupported document worker mode")
    raw_paths = {
        "node": str(env.get("NARRATIIVE_PRESENTATION_NODE") or "").strip(),
        "node_modules": str(env.get("NARRATIIVE_PRESENTATION_NODE_MODULES") or "").strip(),
        "skill_dir": str(env.get("NARRATIIVE_PRESENTATION_SKILL_DIR") or "").strip(),
        "python": str(env.get("NARRATIIVE_PRESENTATION_PYTHON") or "").strip(),
    }
    required = {name: Path(value) for name, value in raw_paths.items() if value}
    missing = [name for name, value in raw_paths.items() if not value]
    missing.extend(
        name
        for name, path in required.items()
        if not path.exists()
        or (name in {"node", "python"} and not path.is_file())
        or (name in {"node_modules", "skill_dir"} and not path.is_dir())
    )
    if missing:
        raise GrowthBlueprintDeliverableWorkerError(
            f"document worker paths are unavailable: {','.join(sorted(set(missing)))}"
        )
    repository_root = Path(__file__).resolve().parents[1]
    render_script = repository_root / "scripts" / "render_growth_blueprint_deliverable.mjs"
    pdf_script = repository_root / "scripts" / "build_pdf_from_slides.py"
    if not render_script.is_file() or not pdf_script.is_file():
        raise GrowthBlueprintDeliverableWorkerError("document worker render scripts are unavailable")
    renderer = LocalArtifactToolPresentationRenderer(
        node=required["node"],
        node_modules=required["node_modules"],
        skill_dir=required["skill_dir"],
        render_script=render_script,
        pdf_script=pdf_script,
        python=required["python"],
    )
    scoped_root = Path(root)
    return GrowthBlueprintDeliverableWorker(
        renderer=renderer,
        store=FileDeliverableStore(scoped_root / "deliverable-records"),
        output_root=scoped_root / "deliverables",
    )
