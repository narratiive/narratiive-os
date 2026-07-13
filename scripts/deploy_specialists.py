from __future__ import annotations

import argparse
import json
from pathlib import Path

from runtime.prompt_registry import FilePromptRegistry
from runtime.specialists import SpecialistCatalog, deployment_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and deploy Narratiive OS specialists")
    parser.add_argument("--repository-root", default=".")
    parser.add_argument(
        "--workflow",
        default="workflows/growth_blueprint_pipeline.json",
    )
    parser.add_argument("--registry-root", default=".runtime/prompts")
    parser.add_argument("--output", default=".runtime/specialist-deployment.json")
    args = parser.parse_args()

    repository_root = Path(args.repository_root).resolve()
    registry = FilePromptRegistry(Path(args.registry_root))
    catalog = SpecialistCatalog(repository_root, args.workflow)
    payload = deployment_manifest(catalog.deploy(registry))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
