from __future__ import annotations

import hashlib
from datetime import datetime

from runtime.mission_control import MissionControlSnapshot
from runtime.proactive_change_detection import (
    MaterialChange,
    ProactiveChangeDetector,
    WatchedItem,
)


class MissionControlChangeDetector:
    """Project canonical Mission Control material into durable executive changes.

    Mission Control remains the source of truth. This adapter derives stable,
    workspace-scoped watched items from explicit blockers and approvals only;
    it does not infer commitments or completion from presentation text.
    """

    def __init__(self, detector: ProactiveChangeDetector) -> None:
        self.detector = detector

    def detect(
        self,
        *,
        workspace_id: str,
        snapshot: MissionControlSnapshot,
        now: datetime | None = None,
    ) -> tuple[MaterialChange, ...]:
        canonical_workspace_id = workspace_id.strip()
        if not canonical_workspace_id:
            raise ValueError("workspace_id is required")
        return self.detector.detect(
            self.watched_items(
                workspace_id=canonical_workspace_id,
                snapshot=snapshot,
            ),
            now=now,
        )

    @staticmethod
    def watched_items(
        *, workspace_id: str, snapshot: MissionControlSnapshot
    ) -> tuple[WatchedItem, ...]:
        canonical_workspace_id = workspace_id.strip()
        if not canonical_workspace_id:
            raise ValueError("workspace_id is required")

        items = [
            MissionControlChangeDetector._item(
                workspace_id=canonical_workspace_id,
                kind="blocker",
                summary=summary,
            )
            for summary in snapshot.blockers
        ]
        items.extend(
            MissionControlChangeDetector._item(
                workspace_id=canonical_workspace_id,
                kind="approval",
                summary=summary,
            )
            for summary in snapshot.approvals_required
        )
        return tuple(sorted(items, key=lambda item: item.scope_key))

    @staticmethod
    def _item(*, workspace_id: str, kind: str, summary: str) -> WatchedItem:
        canonical_summary = summary.strip()
        if not canonical_summary:
            raise ValueError(f"Mission Control {kind} entries must be non-empty")
        digest = hashlib.sha256(canonical_summary.encode("utf-8")).hexdigest()[:20]
        return WatchedItem(
            item_id=digest,
            kind=kind,
            summary=canonical_summary,
            client_id=workspace_id,
            workstream_id="mission-control",
        )
