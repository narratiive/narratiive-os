from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.tony_execution_readiness import build_execution_readiness_report, render_execution_readiness


def main() -> int:
    report = build_execution_readiness_report(os.environ)
    print(render_execution_readiness(report))
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0 if report.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
