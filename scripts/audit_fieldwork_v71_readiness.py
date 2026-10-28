"""Inspect a v7.1 review package without contacting providers or changing state."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.fieldwork_v71_readiness import audit_fieldwork_v71


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    package = json.loads(args.package.read_text(encoding="utf-8-sig"))
    if not isinstance(package, dict):
        parser.error("package must be a JSON object")
    report = audit_fieldwork_v71(package)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["structural_inputs_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
