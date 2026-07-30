from __future__ import annotations

import argparse
from pathlib import Path

from runtime.repository_terminology_audit import audit_repository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail when active Narratiive runtime surfaces contain retired terminology."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=str(Path(__file__).resolve().parents[1]),
        help="Repository root to audit.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    findings = audit_repository(args.root)
    for finding in findings:
        replacement = (
            f"; use '{finding.replacement}'" if finding.replacement else ""
        )
        print(
            f"{finding.path}:{finding.line}:{finding.column}: "
            f"retired term '{finding.term}'{replacement}"
        )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
