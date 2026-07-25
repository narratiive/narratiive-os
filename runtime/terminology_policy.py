from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "proposition" / "terminology.json"


@dataclass(frozen=True)
class TerminologyViolation:
    term: str
    start: int
    end: int
    replacement: str | None
    rationale: str


class TerminologyPolicy:
    def __init__(self, payload: dict) -> None:
        self._validate(payload)
        self.version = payload["version"]
        self.approved_terms = tuple(payload.get("approved_terms", ()))
        self.unsettled_terms = tuple(payload.get("unsettled_terms", ()))
        self.retired_terms = tuple(payload["retired_terms"])

    @classmethod
    def from_path(cls, path: str | Path = DEFAULT_POLICY_PATH) -> "TerminologyPolicy":
        with Path(path).open("r", encoding="utf-8") as handle:
            return cls(json.load(handle))

    @staticmethod
    def _validate(payload: dict) -> None:
        if payload.get("status") != "active":
            raise ValueError("Terminology policy must be active")
        if not isinstance(payload.get("version"), str) or not payload["version"].strip():
            raise ValueError("Terminology policy requires a version")

        TerminologyPolicy._validate_named_entries(
            payload.get("approved_terms", []),
            collection_name="approved_terms",
            name_field="term",
            detail_field="use",
        )
        TerminologyPolicy._validate_named_entries(
            payload.get("unsettled_terms", []),
            collection_name="unsettled_terms",
            name_field="concept",
            detail_field="rule",
        )

        entries = payload.get("retired_terms")
        if not isinstance(entries, list) or not entries:
            raise ValueError("Terminology policy requires retired_terms")
        seen: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Each retired term must be an object")
            term = entry.get("term")
            rationale = entry.get("rationale")
            if not isinstance(term, str) or not term.strip():
                raise ValueError("Each retired term requires a non-empty term")
            if not isinstance(rationale, str) or not rationale.strip():
                raise ValueError(f"Retired term '{term}' requires a rationale")
            key = term.casefold()
            if key in seen:
                raise ValueError(f"Duplicate retired term: {term}")
            seen.add(key)

    @staticmethod
    def _validate_named_entries(
        entries: object,
        *,
        collection_name: str,
        name_field: str,
        detail_field: str,
    ) -> None:
        if not isinstance(entries, list):
            raise ValueError(f"Terminology policy {collection_name} must be a list")
        seen: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"Each {collection_name} entry must be an object")
            name = entry.get(name_field)
            detail = entry.get(detail_field)
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Each {collection_name} entry requires {name_field}")
            if not isinstance(detail, str) or not detail.strip():
                raise ValueError(f"{collection_name} entry '{name}' requires {detail_field}")
            key = name.casefold()
            if key in seen:
                raise ValueError(f"Duplicate {collection_name} entry: {name}")
            seen.add(key)

    @staticmethod
    def _pattern(term: str) -> re.Pattern[str]:
        return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)

    def scan(self, text: str) -> list[TerminologyViolation]:
        violations: list[TerminologyViolation] = []
        for entry in self.retired_terms:
            for match in self._pattern(entry["term"]).finditer(text):
                violations.append(TerminologyViolation(entry["term"], match.start(), match.end(), entry.get("replacement"), entry["rationale"]))
        return sorted(violations, key=lambda item: (item.start, item.end))

    def scan_many(self, texts: Iterable[str]) -> list[TerminologyViolation]:
        return [violation for text in texts for violation in self.scan(text)]
