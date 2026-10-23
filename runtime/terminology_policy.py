from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "proposition" / "terminology.json"


def customer_identity_phrases(
    payload: Mapping[str, Any],
    *,
    entity_id: str = "",
    client_id: str = "",
) -> tuple[str, ...]:
    """Return every supported explicit customer identity in stable precedence order."""
    values: list[Any] = [payload.get("company"), payload.get("company_name")]
    for field in ("commercial_context", "company_context", "client_context"):
        context = payload.get(field)
        if isinstance(context, Mapping):
            values.extend(
                (
                    context.get("company"),
                    context.get("company_name"),
                    context.get("brand_name"),
                    context.get("name"),
                )
            )
    values.extend((entity_id, client_id))
    return tuple(
        dict.fromkeys(str(value).strip() for value in values if str(value or "").strip())
    )


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
        self.version = payload["version"].strip()
        self.version_note = payload["version_note"].strip()
        self.approved_terms = tuple(payload.get("approved_terms", ()))
        self.unsettled_terms = tuple(payload.get("unsettled_terms", ()))
        self.customer_facing_aliases = tuple(payload.get("customer_facing_aliases", ()))
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
        if not isinstance(payload.get("version_note"), str) or not payload["version_note"].strip():
            raise ValueError("Terminology policy requires a version_note")

        approved_names = TerminologyPolicy._validate_named_entries(
            payload.get("approved_terms", []),
            collection_name="approved_terms",
            name_field="term",
            detail_field="use",
        )
        unsettled_names = TerminologyPolicy._validate_named_entries(
            payload.get("unsettled_terms", []),
            collection_name="unsettled_terms",
            name_field="concept",
            detail_field="rule",
        )
        TerminologyPolicy._validate_aliases(payload.get("customer_facing_aliases", []))

        entries = payload.get("retired_terms")
        if not isinstance(entries, list) or not entries:
            raise ValueError("Terminology policy requires retired_terms")
        retired_names: dict[str, str] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Each retired term must be an object")
            term = entry.get("term")
            rationale = entry.get("rationale")
            if not isinstance(term, str) or not term.strip():
                raise ValueError("Each retired term requires a non-empty term")
            if not isinstance(rationale, str) or not rationale.strip():
                raise ValueError(f"Retired term '{term}' requires a rationale")
            replacement = entry.get("replacement")
            if replacement is not None and (not isinstance(replacement, str) or not replacement.strip()):
                raise ValueError(f"Retired term '{term}' replacement must be null or non-empty text")
            key = TerminologyPolicy._normalise_name(term)
            if key in retired_names:
                raise ValueError(f"Duplicate retired term: {term}")
            retired_names[key] = term

        TerminologyPolicy._reject_collection_overlap(
            approved_names,
            retired_names,
            left_name="approved_terms",
            right_name="retired_terms",
        )
        TerminologyPolicy._reject_collection_overlap(
            unsettled_names,
            retired_names,
            left_name="unsettled_terms",
            right_name="retired_terms",
        )
        TerminologyPolicy._reject_collection_overlap(
            approved_names,
            unsettled_names,
            left_name="approved_terms",
            right_name="unsettled_terms",
        )

    @staticmethod
    def _normalise_name(value: str) -> str:
        return " ".join(value.split()).casefold()

    @staticmethod
    def _validate_aliases(entries: object) -> None:
        if not isinstance(entries, list):
            raise ValueError("Terminology policy customer_facing_aliases must be a list")
        seen: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Each customer_facing_aliases entry must be an object")
            term = entry.get("term")
            replacement = entry.get("replacement")
            rationale = entry.get("rationale")
            if not isinstance(term, str) or not term.strip():
                raise ValueError("Each customer_facing_aliases entry requires term")
            if not isinstance(replacement, str) or not replacement.strip():
                raise ValueError(f"Customer-facing alias '{term}' requires replacement")
            if not isinstance(rationale, str) or not rationale.strip():
                raise ValueError(f"Customer-facing alias '{term}' requires rationale")
            key = TerminologyPolicy._normalise_name(term)
            if key in seen:
                raise ValueError(f"Duplicate customer-facing alias: {term}")
            seen.add(key)

    @staticmethod
    def _reject_collection_overlap(
        left: dict[str, str],
        right: dict[str, str],
        *,
        left_name: str,
        right_name: str,
    ) -> None:
        overlap = sorted(set(left).intersection(right))
        if not overlap:
            return
        key = overlap[0]
        raise ValueError(
            f"Terminology entry '{left[key]}' cannot appear in both "
            f"{left_name} and {right_name}"
        )

    @staticmethod
    def _validate_named_entries(
        entries: object,
        *,
        collection_name: str,
        name_field: str,
        detail_field: str,
    ) -> dict[str, str]:
        if not isinstance(entries, list):
            raise ValueError(f"Terminology policy {collection_name} must be a list")
        seen: dict[str, str] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"Each {collection_name} entry must be an object")
            name = entry.get(name_field)
            detail = entry.get(detail_field)
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Each {collection_name} entry requires {name_field}")
            if not isinstance(detail, str) or not detail.strip():
                raise ValueError(f"{collection_name} entry '{name}' requires {detail_field}")
            key = TerminologyPolicy._normalise_name(name)
            if key in seen:
                raise ValueError(f"Duplicate {collection_name} entry: {name}")
            seen[key] = name
        return seen

    @staticmethod
    def _pattern(term: str) -> re.Pattern[str]:
        flexible_term = r"\s+".join(re.escape(part) for part in term.split())
        return re.compile(rf"(?<!\w){flexible_term}(?!\w)", re.IGNORECASE)

    @staticmethod
    def _product_label_pattern(term: str) -> re.Pattern[str]:
        """Match a product label; known identities are protected by the caller."""
        return TerminologyPolicy._pattern(term)

    def scan(self, text: str) -> list[TerminologyViolation]:
        violations: list[TerminologyViolation] = []
        for entry in self.retired_terms:
            for match in self._pattern(entry["term"]).finditer(text):
                violations.append(
                    TerminologyViolation(
                        entry["term"],
                        match.start(),
                        match.end(),
                        entry.get("replacement"),
                        entry["rationale"],
                    )
                )
        return sorted(violations, key=lambda item: (item.start, item.end))

    def scan_many(self, texts: Iterable[str]) -> list[TerminologyViolation]:
        return [violation for text in texts for violation in self.scan(text)]

    def scan_customer_facing(
        self,
        text: str,
        *,
        protected_phrases: Iterable[str] = (),
    ) -> list[TerminologyViolation]:
        """Find terms that must not pass through a customer-facing boundary."""
        protected_spans = tuple(
            match.span()
            for phrase in protected_phrases
            if str(phrase).strip()
            for match in self._pattern(str(phrase).strip()).finditer(text)
        )
        violations = [
            violation
            for violation in self.scan(text)
            if not any(
                start <= violation.start and violation.end <= end
                for start, end in protected_spans
            )
        ]
        for entry in self.customer_facing_aliases:
            for match in self._product_label_pattern(entry["term"]).finditer(text):
                if any(start <= match.start() and match.end() <= end for start, end in protected_spans):
                    continue
                violations.append(
                    TerminologyViolation(
                        entry["term"],
                        match.start(),
                        match.end(),
                        entry["replacement"],
                        entry["rationale"],
                    )
                )
        return sorted(violations, key=lambda item: (item.start, item.end))

    def scan_customer_facing_many(
        self,
        texts: Iterable[str],
        *,
        protected_phrases: Iterable[str] = (),
    ) -> list[TerminologyViolation]:
        protected = tuple(protected_phrases)
        return [
            violation
            for text in texts
            for violation in self.scan_customer_facing(text, protected_phrases=protected)
        ]

    def rewrite(self, text: str) -> str:
        """Rewrite retired terminology into current descriptive language.

        A policy-supplied replacement is preferred. Where a retired term has no
        explicit replacement, use a deliberately generic description rather than
        blocking an otherwise useful Tony response.
        """
        rewritten = text
        for entry in self.retired_terms:
            replacement = str(entry.get("replacement") or "current Narratiive approach").strip()
            rewritten = self._pattern(entry["term"]).sub(replacement, rewritten)
        return rewritten

    def render_owned_product_copy(self, text: str) -> str:
        """Render system-owned product copy; never pass evidence or client-authored text."""
        rendered = text
        for entry in self.customer_facing_aliases:
            rendered = self._product_label_pattern(entry["term"]).sub(entry["replacement"], rendered)
        return self.rewrite(rendered)
