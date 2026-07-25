from __future__ import annotations

import fcntl
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def engineering_task_lock(
    state_dir: str | Path,
    task_id: str,
    *,
    error_type: type[RuntimeError],
    error_prefix: str,
) -> Iterator[None]:
    """Serialise all durable operations for one validated engineering task."""

    safe_task_id = str(task_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", safe_task_id):
        raise error_type(f"{error_prefix} task_id is invalid")
    lock_root = Path(state_dir) / "engineering-task-locks"
    try:
        lock_root.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            lock_root / f"{safe_task_id}.lock",
            os.O_CREAT | os.O_RDWR,
            0o600,
        )
        with os.fdopen(descriptor, "a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        raise error_type(f"{error_prefix} lock failed closed") from exc
