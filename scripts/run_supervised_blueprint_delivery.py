#!/usr/bin/env python3
"""Run the Issue #471 fictional supervised Growth Blueprint vertical slice."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.artifact_catalog import FileArtifactCatalog
from runtime.deliverable_production import (
    DeliverableProductionService,
    FileDeliverableStore,
    LocalArtifactToolPresentationRenderer,
)
from runtime.supervised_blueprint_delivery import (
    blueprint_markdown,
    build_supervised_blueprint_package,
    qa_markdown,
)


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def write_new_text(path: Path, content: str) -> None:
    encoded = content if content.endswith("\n") else content + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise ValueError(f"immutable output already exists with different content: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8")


def write_new_json(path: Path, value: object) -> None:
    if path.exists():
        try:
            if json.loads(path.read_text(encoding="utf-8")) == value:
                return
        except json.JSONDecodeError:
            pass
    write_new_text(path, json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def write_ledger_csv(path: Path, ledger: Mapping[str, Any]) -> None:
    columns = (
        "evidence_id",
        "classification",
        "claim",
        "value",
        "unit",
        "publisher",
        "source_url",
        "observed_at",
        "confidence",
        "limitations",
        "validation_step",
    )
    rows = []
    for item in ledger["entries"]:
        rows.append({column: item.get(column, "") for column in columns})
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def renderer_from_environment() -> LocalArtifactToolPresentationRenderer:
    names = {
        "node": "NARRATIIVE_PRESENTATION_NODE",
        "node_modules": "NARRATIIVE_PRESENTATION_NODE_MODULES",
        "skill_dir": "NARRATIIVE_PRESENTATION_SKILL_DIR",
        "python": "NARRATIIVE_PRESENTATION_PYTHON",
    }
    raw = {name: str(os.environ.get(env_name) or "").strip() for name, env_name in names.items()}
    paths = {name: Path(value) for name, value in raw.items() if value}
    missing = [
        env_name
        for name, env_name in names.items()
        if not raw[name] or not paths[name].exists()
    ]
    if missing:
        raise ValueError(f"rendering requires configured paths: {', '.join(missing)}")
    return LocalArtifactToolPresentationRenderer(
        node=paths["node"],
        node_modules=paths["node_modules"],
        skill_dir=paths["skill_dir"],
        render_script=REPOSITORY_ROOT / "scripts" / "render_growth_blueprint_deliverable.mjs",
        pdf_script=REPOSITORY_ROOT / "scripts" / "build_pdf_from_slides.py",
        python=paths["python"],
    )


def repository_path(path: str | Path) -> str:
    candidate = Path(path).resolve()
    try:
        return candidate.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return str(candidate)


def make_render_evidence_portable(output_dir: Path, rendered: dict[str, Any]) -> None:
    rendered["pptx_path"] = repository_path(rendered["pptx_path"])
    rendered["pdf_path"] = repository_path(rendered["pdf_path"])
    validation_source = output_dir.parent / f"{output_dir.name}.validation.json"
    validation_target = output_dir / "presentation-validation.json"
    if validation_source.is_file() and not validation_target.exists():
        shutil.move(str(validation_source), str(validation_target))
    if validation_target.is_file():
        validation = read_object(validation_target)
        first_party_import = validation.get("firstPartyImport")
        if isinstance(first_party_import, dict):
            first_party_import["runtimeNodeModules"] = "bundled-workspace-runtime"
            first_party_import["nodeExecutable"] = "bundled-workspace-runtime"
        validation_target.write_text(
            json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    receipt_path = output_dir / "render-receipt.json"
    if receipt_path.is_file():
        receipt = read_object(receipt_path)
        receipt["pptx"] = rendered["pptx_path"]
        receipt["pdf"] = rendered["pdf_path"]
        receipt["validation"] = repository_path(validation_target)
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    review_path = output_dir / "rendered-review.json"
    if review_path.is_file():
        review = read_object(review_path)
        if review.get("ocr_output"):
            review["ocr_output"] = repository_path(review["ocr_output"])
        review_path.write_text(
            json.dumps(review, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()

    intake = read_object(args.intake)
    identity = intake.get("identity") or {}
    workspace_id = str(identity.get("workspace_id") or "")
    package_version = int(identity.get("package_version") or 1)
    catalog = FileArtifactCatalog(args.runtime_root / "artifacts", workspace_id=workspace_id)
    package = build_supervised_blueprint_package(intake, artifact_catalog=catalog)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rendered: dict[str, Any] | None = None
    if args.render:
        service = DeliverableProductionService(
            renderer_from_environment(),
            FileDeliverableStore(args.runtime_root / "deliverable-records"),
        )
        record = service.produce(
            package.blueprint,
            specification=package.presentation,
            deliverable_id=(
                f"{identity['client_id']}-supervised-blueprint-demo-v{package_version}"
            ),
            output_dir=output_dir,
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        rendered = record.to_dict()
        make_render_evidence_portable(output_dir, rendered)

    qa_report = dict(package.qa_report)
    if rendered is not None:
        qa_report["rendered_output"] = rendered
        qa_report["rendered_quality_passed"] = rendered["visual_qa"]["status"] == "passed"
        if not qa_report["rendered_quality_passed"]:
            qa_report["status"] = "REVISE"
            qa_report["recommendation"] = "Repair the rendered review copy before requesting Matt's approval."

    manifest = package.manifest()
    if rendered is not None:
        manifest["rendered_deliverable"] = rendered

    write_new_json(output_dir / "structured-client-intake.json", package.intake)
    write_new_json(output_dir / "evidence-and-assumptions-ledger.json", package.evidence_ledger)
    write_ledger_csv(output_dir / "evidence-and-assumptions-ledger.csv", package.evidence_ledger)
    write_new_json(output_dir / "commercial-opportunity-model.json", package.commercial_model)
    write_new_json(output_dir / "seven-chapter-blueprint.json", package.blueprint)
    company_slug = "-".join(str(package.intake["identity"]["company_name"]).strip().split())
    write_new_text(output_dir / f"Narratiive-Growth-Blueprint-{company_slug}-fictional.md", blueprint_markdown(package))
    write_new_json(output_dir / "presentation-specification.json", package.presentation.to_dict())
    write_new_json(output_dir / "independent-qa-report.json", qa_report)
    write_new_text(output_dir / "independent-qa-report.md", qa_markdown(qa_report))
    write_new_json(output_dir / "human-approval-checkpoint.json", package.approval_checkpoint)
    write_new_json(output_dir / "lineage-manifest.json", manifest)

    print(json.dumps({
        "status": qa_report["status"],
        "output_dir": str(output_dir),
        "approval_status": package.approval_checkpoint["status"],
        "rendered": rendered is not None,
        "external_action_taken": False,
    }, indent=2))
    return 0 if qa_report["status"] == "PASS_FOR_HUMAN_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
