#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib import error, request

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.executive_visibility import ExecutiveVisibilityPolicy
from runtime.inbound_leads import FileInboundLeadStore
from runtime.proactive_executive_delivery import FileDeliveryKeyStore
from scripts.run_proactive_brief import run_brief


class AttentionAcceptanceError(RuntimeError):
    pass


BridgeOpener = Callable[..., Any]
BriefRunner = Callable[..., dict[str, Any]]


def accept_attention_suppression(
    *,
    lead_path: Path,
    runtime_root: Path,
    workspace_id: str,
    bridge_url: str,
    bridge_token: str,
    deployment: dict[str, Any],
    receipt_path: Path,
    opener: BridgeOpener = request.urlopen,
    brief_runner: BriefRunner = run_brief,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not workspace_id.strip():
        raise AttentionAcceptanceError("workspace_id is required")
    if not bridge_token.strip():
        raise AttentionAcceptanceError("TONY_BRIDGE_TOKEN is required")
    deployed_revision = str(deployment.get("deployed_revision") or "").strip()
    if (
        deployment.get("status") != "healthy"
        or deployment.get("smoke_check") != "passed"
        or deployment.get("rolled_back") is not False
        or not deployed_revision
    ):
        raise AttentionAcceptanceError("a healthy deployment receipt is required")

    raw_leads = FileInboundLeadStore(lead_path).read()
    visible_leads = ExecutiveVisibilityPolicy().visible_leads(raw_leads)
    visible_ids = {lead.lead_id for lead in visible_leads}
    hidden_ids = {lead.lead_id for lead in raw_leads} - visible_ids
    if not hidden_ids:
        raise AttentionAcceptanceError(
            "live proof requires at least one persisted suppressed, archived, test, or completed lead"
        )

    morning = _bridge_command(bridge_url, bridge_token, "/morning", opener=opener)
    leads = _bridge_command(bridge_url, bridge_token, "/leads", opener=opener)
    morning_ids = {
        str(item.get("item_id", ""))[5:]
        for item in morning.get("data", {})
        .get("agency_state", {})
        .get("executive_items", [])
        if isinstance(item, dict) and str(item.get("item_id", "")).startswith("lead-")
    }
    lead_ids = {
        str(item.get("lead_id", ""))
        for item in leads.get("data", {}).get("leads", [])
        if isinstance(item, dict) and str(item.get("lead_id", ""))
    }
    loaded_count = morning.get("data", {}).get("inbound_leads_loaded")
    if morning.get("ok") is not True or leads.get("ok") is not True:
        raise AttentionAcceptanceError("live Tony read commands did not succeed")
    if loaded_count != len(visible_ids):
        raise AttentionAcceptanceError("morning brief reported an unexpected visible-lead count")
    if morning_ids != visible_ids or lead_ids != visible_ids:
        raise AttentionAcceptanceError("live Tony projections do not match executive-visible source records")
    if hidden_ids.intersection(morning_ids | lead_ids):
        raise AttentionAcceptanceError("a hidden record escaped into a live executive projection")

    checked_at = now or datetime.now().astimezone()
    delivery_key = f"{workspace_id.strip()}:morning:{checked_at.date().isoformat()}"
    key_store = FileDeliveryKeyStore(
        runtime_root
        / "workspaces"
        / workspace_id.strip()
        / "proactive-delivery"
        / "brief-delivery-keys.json"
    )
    if not key_store.contains(delivery_key):
        raise AttentionAcceptanceError(
            "today's brief has not already been delivered; refusing a probe that could send"
        )
    replay = brief_runner(command="morning", simulate_transport_failure=False)
    if replay.get("status") != "duplicate_suppressed" or replay.get("attempts") != 0:
        raise AttentionAcceptanceError("live brief replay was not suppressed before transport")

    receipt = {
        "schema_version": 1,
        "status": "accepted",
        "checked_at": checked_at.isoformat(),
        "deployed_revision": deployed_revision,
        "workspace_id": workspace_id.strip(),
        "raw_lead_count": len(raw_leads),
        "visible_lead_count": len(visible_ids),
        "hidden_lead_count": len(hidden_ids),
        "visible_lead_ids": sorted(visible_ids),
        "hidden_lead_ids": sorted(hidden_ids),
        "morning_command_status": str(morning.get("status") or ""),
        "lead_command_status": str(leads.get("status") or ""),
        "duplicate_delivery_key": delivery_key,
        "duplicate_status": str(replay.get("status") or ""),
        "duplicate_attempts": replay.get("attempts"),
        "external_action_taken": False,
        "client_workflow_mutations": 0,
    }
    _atomic_json(receipt_path, receipt)
    return receipt


def _bridge_command(
    url: str,
    token: str,
    command: str,
    *,
    opener: BridgeOpener,
) -> dict[str, Any]:
    probe = request.Request(
        url,
        data=json.dumps({"text": command}).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with opener(probe, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, error.URLError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AttentionAcceptanceError(f"live Tony command failed: {command}") from exc
    if not isinstance(payload, dict):
        raise AttentionAcceptanceError(f"live Tony command returned invalid data: {command}")
    return payload


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Prove live executive attention filtering and pre-transport duplicate suppression."
    )
    value.add_argument("--apply", action="store_true")
    value.add_argument("--repository", type=Path, default=REPOSITORY_ROOT)
    value.add_argument("--runtime-root", type=Path)
    value.add_argument("--workspace-id")
    value.add_argument("--bridge-url", default="http://127.0.0.1:8790/")
    value.add_argument("--receipt", type=Path)
    return value


def main() -> int:
    args = parser().parse_args()
    repository = args.repository.resolve()
    runtime_root = (
        args.runtime_root
        or Path(os.getenv("NARRATIIVE_RUNTIME_ROOT", str(repository / ".runtime")))
    ).resolve()
    workspace_id = (
        args.workspace_id
        or os.getenv("TONY_EXECUTIVE_WORKSPACE_ID", "").strip()
        or os.getenv("TONY_GITHUB_WORKSPACE_ID", "").strip()
    )
    receipt_path = (
        args.receipt
        or repository / "runtime-state" / "attention-acceptance.json"
    ).resolve()
    if not args.apply:
        print(
            json.dumps(
                {
                    "status": "ready",
                    "mode": "dry-run",
                    "workspace_id": workspace_id,
                    "receipt": str(receipt_path),
                    "safety": "requires today's existing delivery key; never sends a new brief",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    try:
        deployment = json.loads(
            (repository / "runtime-state" / "deployment.json").read_text(encoding="utf-8")
        )
        receipt = accept_attention_suppression(
            lead_path=Path(
                os.getenv(
                    "TONY_INBOUND_LEADS_PATH",
                    str(repository / ".runtime" / "inbound-leads.json"),
                )
            ).resolve(),
            runtime_root=runtime_root,
            workspace_id=workspace_id,
            bridge_url=args.bridge_url,
            bridge_token=os.getenv("TONY_BRIDGE_TOKEN", ""),
            deployment=deployment,
            receipt_path=receipt_path,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttentionAcceptanceError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
