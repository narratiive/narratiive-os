from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.github_issue_runner import RunnerConfig, run_service


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the bounded Narratiive GitHub issue implementation service"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    run_service(RunnerConfig.load(args.config), once=args.once)


if __name__ == "__main__":
    main()
