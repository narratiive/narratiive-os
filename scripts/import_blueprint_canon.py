#!/usr/bin/env python3
"""Import the canonical Blueprint source exports into the repository.

The script accepts literal exports of the four canonical Google Docs and applies
only deterministic normalization:

- remove a UTF-8 BOM if present
- normalize CRLF/CR line endings to LF
- ensure exactly one trailing newline

It then writes the canon files under ``knowledge/blueprint/`` and recalculates
the manifest checksums for the assets and bundle.
"""

from __future__ import annotations

import argparse
import json
import hashlib
from pathlib import Path
from typing import Any


ASSET_TARGETS = {
    "blueprint_population_system": Path("knowledge/blueprint/population-system.md"),
    "blueprint_schema_v3": Path("knowledge/blueprint/blueprint-schema-v3.md"),
    "visual_framework_library_v1": Path("knowledge/blueprint/visual-framework-library-v1.md"),
    "visual_intelligence_system_v1": Path("knowledge/blueprint/visual-intelligence-system-v1.md"),
}


def normalize_export_bytes(raw_bytes: bytes) -> str:
    text = raw_bytes.decode("utf-8")
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def update_manifest(manifest_path: Path, assets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for asset in manifest.get("assets", []):
        asset_id = asset.get("asset_id")
        if asset_id not in assets:
            continue
        asset["checksum"] = assets[asset_id]["checksum"]
    for bundle in manifest.get("bundles", []):
        if not isinstance(bundle, dict):
            continue
        components = []
        for component in bundle.get("components", []):
            component_asset = assets.get(component.get("asset_id"))
            if component_asset is None:
                continue
            component["checksum"] = component_asset["checksum"]
            components.append(
                {
                    "asset_id": component["asset_id"],
                    "version": component["version"],
                    "checksum": component["checksum"],
                    "repository_path": component["repository_path"],
                }
            )
        bundle["checksum"] = sha256_hex(
            stable_json(
                {
                    "bundle_id": bundle["bundle_id"],
                    "version": bundle["version"],
                    "canon_version": bundle.get("canon_version", bundle["version"]),
                    "status": bundle["status"],
                    "prompt_asset_id": bundle["prompt_asset_id"],
                    "supporting_asset_ids": list(bundle["supporting_asset_ids"]),
                    "components": components,
                    "compatibility_notes": list(bundle.get("compatibility_notes", [])),
                }
            )
        )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--manifest", default="knowledge/blueprint/manifest.json")
    parser.add_argument("--blueprint-population-system", required=True)
    parser.add_argument("--blueprint-schema-v3", required=True)
    parser.add_argument("--visual-framework-library-v1", required=True)
    parser.add_argument("--visual-intelligence-system-v1", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    manifest_path = (repo_root / args.manifest).resolve()

    source_map = {
        "blueprint_population_system": Path(args.blueprint_population_system),
        "blueprint_schema_v3": Path(args.blueprint_schema_v3),
        "visual_framework_library_v1": Path(args.visual_framework_library_v1),
        "visual_intelligence_system_v1": Path(args.visual_intelligence_system_v1),
    }

    report: dict[str, Any] = {"repo_root": str(repo_root), "manifest": str(manifest_path), "assets": {}}
    asset_updates: dict[str, dict[str, Any]] = {}
    for asset_id, source_path in source_map.items():
        target_path = repo_root / ASSET_TARGETS[asset_id]
        raw_bytes = source_path.read_bytes()
        normalized = normalize_export_bytes(raw_bytes)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(normalized, encoding="utf-8")
        checksum = sha256_hex(normalized)
        asset_updates[asset_id] = {"checksum": checksum}
        report["assets"][asset_id] = {
            "source_path": str(source_path),
            "target_path": str(target_path),
            "source_chars": len(raw_bytes.decode("utf-8")),
            "repo_chars": len(normalized),
            "checksum": checksum,
        }

    manifest = update_manifest(manifest_path, asset_updates)
    report["bundle_checksum"] = manifest["bundles"][0]["checksum"] if manifest.get("bundles") else ""
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
