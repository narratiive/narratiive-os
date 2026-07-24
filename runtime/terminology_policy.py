from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parents[1]
    / "knowledge"
    / "proposition"
    / "terminology.json"
)


@dataclass(frozen=True)
class TerminologyViolation:
    term: str
    start: int
    end: int
    replacement: str | None
    rationale: str

    @property
    def message(self) -> str:
        replacement = (
            f" Use '{self.replacement}' instead."
            if self.replacement
            else " No replacement is approved; resolve the wording from the canonical proposition."
        )
        return f"Retired term '{self.term}' is not permitted.{replacement}"


class TerminologyPolicy:
    def __init__(self, payload: dict) -> None:
        self._validate_payload(payload)
        self.version = payload["version"]
        self.status = payload["status"]
        self.approved_terms = tuple(payload.get("approved_terms", ()))
        self.unsettled_terms = tuple(payload.get("unsettled_terms", ()))
        self.retired_terms = tuple(payload["retired_terms"])

    @classmethod
    def from_path(cls, path: str | Path = DEFAULT_POLICY_PATH) -> "TerminologyPolicy":
        with Path(path).open("r", encoding="utf-8") as handle:
            return cls(json.load(handle))

    @staticmethod
    def _validate_payload(payload: dict) -> None:
        if payload.get("status") != "active":
            raise ValueError("Terminology policy must be active")
        if not isinstance(payload.get("version"), str) or not payload["version"].strip():
            raise ValueError("Terminology policy requires a version")
        retired_terms = payload.get("retired_terms")
        if not isinstance(retired_terms, list) or not retired_terms:
            raise ValueError("Terminology policy requires retired_terms")
        normalized: set[str] = set()
        for entry in retired_terms:
            if not isinstance(entry, dict):
                raise ValueError("Each retired term must be an object")
            term = entry.get("term")
            rationale = entry.get("rationale")
            if not isinstance(term, str) or not term.strip():
                raise ValueError("Each retired term requires a non-empty term")
            if not isinstance(rationale, str) or not rationale.strip():
                raise ValueError(f"Retired term '{term}' requires a rationale")
            key = term.casefold()
            if key in normalized:
                raise ValueError(f"Duplicate retired term: {term}")
            normalized.add(key)

    @staticmethod
    def _pattern(term: str) -> re.Pattern[str]:
        return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)

    def scan(self, text: str) -> list[TerminologyViolation]:
        violations: list[TerminologyViolation] = []
        for entry in self.retired_terms:
            for match in self._pattern(entry["term"]).finditer(text):
                violations.append(
                    TerminologyViolation(
                        term=entry["term"],
                        start=match.start(),
                        end=match.end(),
                        replacement=entry.get("replacement"),
                        rationale=entry["rationale"],
                    )
                )
        return sorted(violations, key=lambda item: (item.start, item.end))

    def require_current(self, text: str) -> None:
        violations = self.scan(text)
        if violations:
            messages = "; ".join(item.message for item in violations)
            raise ValueError(messages)

    def scan_many(self, texts: Iterable[str]) -> list[TerminologyViolation]:
        violations: list[TerminologyViolation] = []
        for text in texts:
            violations.extend(self.scan(text))
        return violations
