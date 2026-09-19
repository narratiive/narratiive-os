from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from runtime.campaign_learning import CampaignLearningCycle


NotionDispatcher = Callable[[dict[str, Any]], dict[str, Any]]


class CampaignLearningProjectionService:
    """Approval-gated, idempotent projection of learning records into Notion."""

    def __init__(self, root: str | Path, dispatcher: NotionDispatcher | None = None) -> None:
        self.root = Path(root)
        self.events_path = self.root / "events.jsonl"
        self.lock_path = self.root / ".lock"
        self.dispatcher = dispatcher

    def prepare(self, cycle: CampaignLearningCycle) -> dict[str, Any]:
        projection = self._projection(cycle)
        with self._lock():
            events = self._events()
            complete = self._event(events, projection["projection_key"], {"verified", "reconciled"})
            if complete:
                return {**projection, "projection_status": "verified", "record_id": complete.get("record_id")}
            existing = self._event(events, projection["projection_key"], {"prepared", "dispatching", "failed"})
            if not existing:
                self._append({"event": "prepared", **projection, "recorded_at": _now()})
            return {**projection, "projection_status": str((existing or {}).get("event") or "prepared")}

    def sync(self, cycle: CampaignLearningCycle, *, approver: str, rationale: str) -> dict[str, Any]:
        if not approver.strip() or not rationale.strip():
            raise ValueError("Notion learning projection requires authenticated approval and rationale")
        approver_tokens = {
            token for token in re.split(r"[^a-z0-9]+", approver.strip().casefold()) if token
        }
        if "matt" not in approver_tokens:
            raise ValueError("Notion learning projection requires Matt's authenticated identity")
        projection = self.prepare(cycle)
        key = projection["projection_key"]
        if self.dispatcher is None:
            return {**projection, "projection_status": "notion_dispatcher_unavailable", "external_action_taken": False}
        with self._lock():
            events = self._events()
            complete = self._event(events, key, {"verified", "reconciled"})
            if complete:
                return {
                    **projection,
                    "projection_status": "duplicate_suppressed",
                    "record_id": complete.get("record_id"),
                    "external_action_taken": False,
                }
            if self._event(events, key, {"dispatching", "failed"}):
                return {**projection, "projection_status": "reconciliation_required", "external_action_taken": False}
            self._append({
                "event": "dispatching",
                "projection_key": key,
                "cycle_id": cycle.cycle_id,
                "approved_by": approver.strip(),
                "rationale": rationale.strip(),
                "recorded_at": _now(),
            })
        dispatch = {
            "worker": "Notion",
            "state": "approved_pending_execution",
            "execution_mode": "approval_gated_write",
            "approval_granted": True,
            "approval_scope": "campaign_learning_projection",
            "execution_truth": "not_dispatched",
            "idempotency_key": key,
            "target": {
                "workspace_id": cycle.performance.identity.workspace_id,
                "client_id": cycle.performance.identity.client_id,
                "campaign_id": cycle.performance.identity.campaign_id,
                "area": "campaign_learning",
            },
            "payload": {"kind": "campaign_learning_projection", **projection},
            "instruction": (
                "Project this exact Performance → Insight → Creative Iteration cycle onto the matching Notion "
                "campaign record. Preserve pending human approval. Do not change media, publish, spend or execute iteration work."
            ),
            "expected_evidence": "verified Notion mutation with record identifier and exact projection key",
            "return_to": "Tony",
        }
        try:
            evidence = self.dispatcher(dispatch)
        except Exception as exc:
            self._record_failure(key, cycle.cycle_id, f"dispatch_error:{type(exc).__name__}")
            return {**projection, "projection_status": "reconciliation_required", "external_action_taken": False}
        record_id = str(evidence.get("record_id") or evidence.get("page_id") or "").strip() if isinstance(evidence, Mapping) else ""
        returned_key = str(evidence.get("projection_key") or evidence.get("idempotency_key") or "").strip() if isinstance(evidence, Mapping) else ""
        returned_cycle = str(evidence.get("cycle_checksum") or "").strip() if isinstance(evidence, Mapping) else ""
        if (
            not isinstance(evidence, Mapping)
            or evidence.get("external_action_taken") is not True
            or not record_id
            or returned_key != key
            or returned_cycle != cycle.checksum
        ):
            self._record_failure(key, cycle.cycle_id, "unverified_notion_evidence")
            return {**projection, "projection_status": "reconciliation_required", "external_action_taken": False}
        with self._lock():
            self._append({
                "event": "verified",
                "projection_key": key,
                "cycle_id": cycle.cycle_id,
                "cycle_checksum": cycle.checksum,
                "record_id": record_id,
                "recorded_at": _now(),
            })
        return {
            **projection,
            "projection_status": "verified",
            "record_id": record_id,
            "external_action_taken": True,
        }

    def _projection(self, cycle: CampaignLearningCycle) -> dict[str, Any]:
        identity = cycle.performance.identity
        payload = {
            "workspace_id": identity.workspace_id,
            "client_id": identity.client_id,
            "brand_id": identity.brand_id,
            "market_ids": list(identity.market_ids),
            "product_ids": list(identity.product_ids),
            "campaign_id": identity.campaign_id,
            "learning_cycle_id": cycle.cycle_id,
            "learning_cycle_checksum": cycle.checksum,
            "performance_record_id": cycle.performance.record_id,
            "performance_period": {
                "start": cycle.performance.period_start,
                "end": cycle.performance.period_end,
            },
            "providers": list(cycle.performance.providers),
            "mapped_asset_version_ids": list(cycle.performance.mapped_asset_version_ids),
            "insights": [
                {
                    "insight_id": item.insight_id,
                    "severity": item.severity,
                    "category": item.category,
                    "summary": item.summary,
                    "evidence_grade": item.evidence_grade,
                    "human_review_required": item.human_review_required,
                }
                for item in cycle.insights
            ],
            "iteration_proposals": [
                {
                    "proposal_id": item.proposal_id,
                    "source_insight_id": item.source_insight_id,
                    "source_asset_version_ids": list(item.source_asset_version_ids),
                    "objective": item.objective,
                    "hypothesis": item.hypothesis,
                    "status": item.status,
                    "production_authorised": item.production_authorised,
                    "publication_authorised": item.publication_authorised,
                    "media_spend_authorised": item.media_spend_authorised,
                }
                for item in cycle.iteration_proposals
            ],
            "operational_status": "learning_pending_human_review",
            "recommended_next_action": "Matt reviews evidence-graded insights and any bounded creative iteration proposal.",
            "publication_authorised": False,
            "media_spend_authorised": False,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return {**payload, "projection_key": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}

    def _record_failure(self, key: str, cycle_id: str, reason: str) -> None:
        with self._lock():
            self._append({
                "event": "failed",
                "projection_key": key,
                "cycle_id": cycle_id,
                "reason": reason,
                "recorded_at": _now(),
            })

    def _events(self) -> list[dict[str, Any]]:
        try:
            lines = self.events_path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        events = []
        for line in lines:
            try:
                item = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise RuntimeError("campaign learning projection history is malformed") from exc
            if not isinstance(item, dict):
                raise RuntimeError("campaign learning projection history is malformed")
            events.append(item)
        return events

    @staticmethod
    def _event(events: list[dict[str, Any]], key: str, kinds: set[str]) -> dict[str, Any] | None:
        return next((item for item in reversed(events) if item.get("projection_key") == key and item.get("event") in kinds), None)

    def _append(self, event: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(event), sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
