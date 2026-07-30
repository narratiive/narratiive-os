from pathlib import Path

from runtime.executive_memory import ExecutiveMemoryStore, MemoryKind, MemoryScope


def test_memory_survives_restart_and_verifies(tmp_path: Path) -> None:
    path = tmp_path / "executive-memory.jsonl"
    store = ExecutiveMemoryStore(path)
    first = store.append(
        kind=MemoryKind.DECISION,
        summary="Prioritise client delivery",
        scope=MemoryScope(client_id="client-a", run_id="run-1"),
        importance=5,
        requires_matt=True,
    )

    restarted = ExecutiveMemoryStore(path)
    selected = restarted.select(scope=MemoryScope(client_id="client-a", run_id="run-1"))

    assert selected[0].record_id == first.record_id
    assert restarted.verify() is True


def test_client_and_run_scope_do_not_leak(tmp_path: Path) -> None:
    store = ExecutiveMemoryStore(tmp_path / "memory.jsonl")
    store.append(
        kind=MemoryKind.CONTEXT,
        summary="Client A context",
        scope=MemoryScope(client_id="client-a", run_id="run-a"),
    )
    store.append(
        kind=MemoryKind.CONTEXT,
        summary="Client B context",
        scope=MemoryScope(client_id="client-b", run_id="run-b"),
    )

    selected = store.select(scope=MemoryScope(client_id="client-a", run_id="run-a"))

    assert [record.summary for record in selected] == ["Client A context"]


def test_retrieval_is_deterministic_and_filterable(tmp_path: Path) -> None:
    store = ExecutiveMemoryStore(tmp_path / "memory.jsonl")
    scope = MemoryScope(workstream_id="commercial")
    store.append(kind=MemoryKind.CONTEXT, summary="Low priority", scope=scope, importance=1)
    store.append(
        kind=MemoryKind.COMMITMENT,
        summary="Follow up prospect",
        scope=scope,
        importance=4,
        requires_matt=False,
    )
    store.append(
        kind=MemoryKind.APPROVAL,
        summary="Pricing approval required",
        scope=scope,
        importance=5,
        requires_matt=True,
    )

    selected = store.select(
        scope=scope,
        minimum_importance=4,
        requires_matt=True,
        limit=5,
    )

    assert [record.summary for record in selected] == ["Pricing approval required"]


def test_hash_chain_detects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "memory.jsonl"
    store = ExecutiveMemoryStore(path)
    store.append(kind=MemoryKind.DECISION, summary="Original decision")
    path.write_text(path.read_text().replace("Original decision", "Changed decision"), encoding="utf-8")

    assert ExecutiveMemoryStore(path).verify() is False


def test_snapshot_is_atomic_copy(tmp_path: Path) -> None:
    store = ExecutiveMemoryStore(tmp_path / "memory.jsonl")
    store.append(kind=MemoryKind.OUTCOME, summary="Delivery complete")

    target = store.snapshot(tmp_path / "snapshots" / "latest.jsonl")

    assert target.read_text(encoding="utf-8") == store.path.read_text(encoding="utf-8")
