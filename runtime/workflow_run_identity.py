from __future__ import annotations

import hashlib


MAX_PERSISTED_RUN_ID_LENGTH = 180


def downstream_run_id(source_run_id: str, workflow_id: str) -> str:
    """Return a deterministic, filesystem-safe downstream run identity.

    Existing short identities retain their historical shape. Long chains keep a
    readable target-workflow suffix while binding the full source and target to
    a stable digest; source lineage remains persisted separately by the handoff.
    """

    candidate = f"{source_run_id}-{workflow_id}"
    if len(candidate) <= MAX_PERSISTED_RUN_ID_LENGTH:
        return candidate
    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:20]
    suffix = f"-{workflow_id}-{digest}"
    prefix_length = MAX_PERSISTED_RUN_ID_LENGTH - len(suffix)
    if prefix_length <= 0:
        return f"run-{digest}"
    return f"{source_run_id[:prefix_length].rstrip('-')}{suffix}"
