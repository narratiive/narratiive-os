from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.blueprint_knowledge_registry import BlueprintKnowledgeRegistry


RAVE_CALIBRE_STANDARD = "Rave Coffee Growth Blueprint calibre, not content template"
_PRESENTATION_GUIDANCE = Path(__file__).resolve().parents[1] / "knowledge" / "blueprint" / "presentation-design-system-v1.md"


class BlueprintDirectorLearningStore:
    """Append-only, bounded-retrieval learning from Matt's Blueprint reviews."""

    def __init__(self, path: str | Path, *, retrieval_limit: int = 3) -> None:
        self.path = Path(path)
        self.retrieval_limit = max(1, min(int(retrieval_limit), 5))

    def record_review(
        self,
        *,
        workspace_id: str,
        client_id: str,
        reviewer: str,
        accepted_strengths: list[str],
        rejected_weaknesses: list[str],
        revision_reason: str,
        final_approved_artifact_reference: Mapping[str, Any] | None,
        quality_review_result: Mapping[str, Any],
        approved: bool,
    ) -> dict[str, Any]:
        reviewer_tokens = {
            token for token in _tokens(reviewer) if token
        }
        if "matt" not in reviewer_tokens:
            raise ValueError("Blueprint Director learning requires Matt's review")
        if approved and not final_approved_artifact_reference:
            raise ValueError("positive Blueprint learning requires the final approved artefact reference")
        quality_passed = quality_review_result.get("passed") is True
        positive_exemplar = bool(approved and quality_passed)
        record = {
            "record_id": "blueprint-learning-" + hashlib.sha256(
                json.dumps(
                    {
                        "workspace_id": workspace_id,
                        "client_id": client_id,
                        "approved": approved,
                        "artifact": dict(final_approved_artifact_reference or {}),
                        "quality": dict(quality_review_result),
                        "revision_reason": revision_reason,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
            ).hexdigest()[:20],
            "workspace_id": workspace_id,
            "client_id": client_id,
            "reviewer": reviewer.strip(),
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "accepted_strengths": _bounded_text_list(accepted_strengths),
            "rejected_weaknesses": _bounded_text_list(rejected_weaknesses),
            "revision_reason": _bounded_text(revision_reason),
            "final_approved_artifact_reference": dict(final_approved_artifact_reference or {}),
            "quality_review_result": dict(quality_review_result),
            "approved": bool(approved),
            "positive_exemplar": positive_exemplar,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing = {item.get("record_id") for item in self._records()}
        if record["record_id"] not in existing:
            line = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str) + "\n"
            descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                os.write(descriptor, line.encode("utf-8"))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return record

    def retrieve(self, *, workspace_id: str, client_id: str) -> dict[str, Any]:
        relevant = [
            item for item in self._records()
            if item.get("workspace_id") == workspace_id
            and item.get("client_id") == client_id
        ]
        positives = [item for item in relevant if item.get("positive_exemplar") is True]
        failures = [item for item in relevant if item.get("positive_exemplar") is not True]
        positive_limit = min(2, self.retrieval_limit)
        selected_positives = positives[-positive_limit:]
        remaining = self.retrieval_limit - len(selected_positives)
        selected_failures = failures[-remaining:] if remaining else []
        return {
            "positive_exemplars": [self._lesson(item, positive=True) for item in selected_positives],
            "failure_patterns": [self._lesson(item, positive=False) for item in selected_failures],
            "retrieval_limit": self.retrieval_limit,
            "canonical_prompt_rewrite_allowed": False,
        }

    def _records(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        records: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                records.append(value)
        return records

    @staticmethod
    def _lesson(record: Mapping[str, Any], *, positive: bool) -> dict[str, Any]:
        lesson = {
            "accepted_strengths": list(record.get("accepted_strengths") or [])[:5],
            "rejected_weaknesses": list(record.get("rejected_weaknesses") or [])[:5],
            "revision_reason": _bounded_text(record.get("revision_reason")),
            "quality_review_result": dict(record.get("quality_review_result") or {}),
        }
        if positive:
            lesson["approved_artifact_reference"] = dict(
                record.get("final_approved_artifact_reference") or {}
            )
        return lesson


class BlueprintDirectorCommissionBuilder:
    """Supply the editorial commission with verified canon and bounded learning."""

    def __init__(
        self,
        *,
        knowledge_registry: BlueprintKnowledgeRegistry | None = None,
        learning_store: BlueprintDirectorLearningStore | None = None,
        presentation_guidance_path: str | Path = _PRESENTATION_GUIDANCE,
    ) -> None:
        self.knowledge_registry = knowledge_registry or BlueprintKnowledgeRegistry.from_default()
        self.learning_store = learning_store
        self.presentation_guidance_path = Path(presentation_guidance_path)

    def enrich(
        self,
        inputs: Mapping[str, Any],
        *,
        workspace_id: str,
        client_id: str,
    ) -> dict[str, Any]:
        bundle = self.knowledge_registry.active_bundle()
        prompt_asset = self.knowledge_registry.prompt_asset(bundle)
        schema = self.knowledge_registry.schema()
        presentation_guidance = self.presentation_guidance_path.read_text(encoding="utf-8")
        result = dict(inputs)
        result["canonical_blueprint_guidance"] = {
            "bundle": bundle.to_dict(),
            "population_guidance": prompt_asset.read_text(self.knowledge_registry.root),
            "slide_architecture": schema.to_dict(),
        }
        result["rave_calibre_reference"] = {
            "standard": RAVE_CALIBRE_STANDARD,
            "usage": "Calibrate ambition, editorial rhythm and founder-grade usefulness only.",
            "prohibition": "Do not copy Rave structure, wording, facts, strategy or content.",
            "content_template": False,
            "presentation_guidance": presentation_guidance,
        }
        result["approved_blueprint_lessons"] = (
            self.learning_store.retrieve(workspace_id=workspace_id, client_id=client_id)
            if self.learning_store is not None
            else {
                "positive_exemplars": [],
                "failure_patterns": [],
                "retrieval_limit": 0,
                "canonical_prompt_rewrite_allowed": False,
            }
        )
        return result


def _tokens(value: Any) -> list[str]:
    token = ""
    result: list[str] = []
    for character in str(value or "").casefold():
        if character.isalnum():
            token += character
        elif token:
            result.append(token)
            token = ""
    if token:
        result.append(token)
    return result


def _bounded_text(value: Any, limit: int = 800) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _bounded_text_list(values: list[str], *, maximum: int = 8) -> list[str]:
    return [_bounded_text(value) for value in values[:maximum] if _bounded_text(value)]
