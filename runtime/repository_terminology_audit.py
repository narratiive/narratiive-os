from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from runtime.terminology_policy import TerminologyPolicy

AUDITED_ROOTS = ("runtime", "openclaw", "scripts", "prompts")
AUDITED_SUFFIXES = frozenset({".json", ".md", ".py", ".toml", ".txt", ".yaml", ".yml"})
IGNORED_PARTS = frozenset({".git", "__pycache__", ".pytest_cache", ".mypy_cache"})


@dataclass(frozen=True)
class RepositoryTerminologyFinding:
    path: str
    line: int
    column: int
    term: str
    replacement: str | None
    rationale: str


def _candidate_files(root: Path, audited_roots: Iterable[str]) -> tuple[Path, ...]:
    candidates: list[Path] = []
    for relative_root in audited_roots:
        directory = root / relative_root
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.casefold() not in AUDITED_SUFFIXES:
                continue
            if any(part in IGNORED_PARTS for part in path.relative_to(root).parts):
                continue
            candidates.append(path)
    return tuple(sorted(candidates, key=lambda path: path.relative_to(root).as_posix()))


def _line_and_column(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    previous_newline = text.rfind("\n", 0, offset)
    column = offset + 1 if previous_newline == -1 else offset - previous_newline
    return line, column


def audit_repository(
    root: str | Path,
    *,
    policy: TerminologyPolicy | None = None,
    audited_roots: Iterable[str] = AUDITED_ROOTS,
) -> tuple[RepositoryTerminologyFinding, ...]:
    repository_root = Path(root).resolve()
    terminology = policy or TerminologyPolicy.from_path()
    findings: list[RepositoryTerminologyFinding] = []

    for path in _candidate_files(repository_root, audited_roots):
        text = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(repository_root).as_posix()
        for violation in terminology.scan(text):
            line, column = _line_and_column(text, violation.start)
            findings.append(
                RepositoryTerminologyFinding(
                    path=relative_path,
                    line=line,
                    column=column,
                    term=violation.term,
                    replacement=violation.replacement,
                    rationale=violation.rationale,
                )
            )

    return tuple(
        sorted(
            findings,
            key=lambda item: (item.path, item.line, item.column, item.term.casefold()),
        )
    )
