from __future__ import annotations

from runtime.github_work import GitHubWorkItem, GitHubWorkSnapshot
from runtime.mission_control import WorkstreamStatus


def project_github_workstreams(
    snapshot: GitHubWorkSnapshot | None,
) -> tuple[WorkstreamStatus, ...]:
    """Project canonical GitHub work into deterministic Mission Control workstreams."""
    if snapshot is None:
        return ()

    approval_keys = {
        (item.kind, item.number) for item in snapshot.matt_approval_required
    }
    items = sorted(
        snapshot.all_open_items,
        key=lambda item: (item.kind, item.number),
    )
    return tuple(
        _project_item(item, approval_keys=approval_keys)
        for item in items
    )


def _project_item(
    item: GitHubWorkItem,
    *,
    approval_keys: set[tuple[str, int]],
) -> WorkstreamStatus:
    blocker = "; ".join(item.blocker_reasons) or None
    requires_matt = (item.kind, item.number) in approval_keys

    if blocker:
        state = "blocked"
        next_action = "Resolve the recorded repository blocker."
    elif requires_matt:
        state = "tested"
        next_action = "Record Matt's review decision."
    else:
        state = "known"
        next_action = "Advance through the recorded repository workflow."

    kind_label = "PR" if item.kind == "pull_request" else "Issue"
    return WorkstreamStatus(
        workstream_id=f"github:{item.kind}:{item.number}",
        title=f"{kind_label} #{item.number}: {item.title}",
        state=state,
        owner="repository",
        next_action=next_action,
        evidence=(item.evidence,),
        blocker=blocker,
        last_updated_at=item.updated_at,
    )
