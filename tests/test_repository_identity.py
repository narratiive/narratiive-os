from __future__ import annotations

import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_REPOSITORY_NAME = "narratiive-" + "knowledge"
CANONICAL_LOCAL_PATH = "~/Documents/narratiive-os"


class RepositoryIdentityTests(unittest.TestCase):
    def test_governance_records_canonical_local_checkout(self) -> None:
        governance = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(CANONICAL_LOCAL_PATH, governance)
        self.assertIn(".venv/bin/python", governance)

    def test_retired_repository_name_is_not_reintroduced(self) -> None:
        findings: list[str] = []
        ignored_roots = {".git", ".venv", ".runtime", "runtime-state", "__pycache__"}
        text_suffixes = {".md", ".py", ".json", ".yml", ".yaml", ".txt", ".sh", ".toml"}

        for path in REPOSITORY_ROOT.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in text_suffixes:
                continue
            if any(part in ignored_roots for part in path.parts):
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if FORBIDDEN_REPOSITORY_NAME in content:
                findings.append(str(path.relative_to(REPOSITORY_ROOT)))

        self.assertEqual(
            findings,
            [],
            f"Retired repository name found in: {', '.join(findings)}",
        )


if __name__ == "__main__":
    unittest.main()
