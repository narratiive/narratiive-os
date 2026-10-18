from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.media_provider_transports import build_configured_media_adapters  # noqa: E402
from runtime.tony_dispatch_adapters import build_http_dispatchers  # noqa: E402
from scripts.execute_tony_safe_read import execute_payload  # noqa: E402


BUSINESS_SURFACES = (
    "Gmail",
    "Google Calendar",
    "Google Drive",
    "Notion",
    "Fireflies",
)


def _redacted_identifier(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _provider_error(exc: Exception) -> str:
    text = str(exc).strip()
    return text if text and len(text) <= 200 else type(exc).__name__


def _http_json(url: str, *, timeout: float = 15.0) -> tuple[int, Mapping[str, Any]]:
    try:
        with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=timeout) as response:
            payload = json.loads(response.read(1_000_001).decode("utf-8"))
            return int(response.status), payload if isinstance(payload, Mapping) else {}
    except HTTPError as exc:
        return int(exc.code), {}
    except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return 0, {}


def _health_checks() -> dict[str, Any]:
    endpoints = {
        "runtime_gateway": "http://127.0.0.1:8787/health",
        "tony_bridge": "http://127.0.0.1:8790/health",
        "n8n": "http://127.0.0.1:5678/healthz",
    }
    result: dict[str, Any] = {}
    for name, url in endpoints.items():
        status, payload = _http_json(url)
        result[name] = {
            "status": "VERIFIED LIVE" if status == 200 else "NOT WORKING",
            "http_status": status,
            "healthy": status == 200 and (payload.get("ok") is True or payload.get("status") in {"ok", "alive"}),
        }
    return result


def _runtime_observations(environ: Mapping[str, str]) -> dict[str, Any]:
    watcher: dict[str, Any] = {"status": "NOT TESTED"}
    try:
        completed = subprocess.run(
            [
                "launchctl",
                "print",
                f"gui/{os.getuid()}/com.narratiive.gmail-inbox-watch",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        completed = None
    if completed is not None and completed.returncode == 0:
        fields: dict[str, str] = {}
        for raw in completed.stdout.splitlines():
            line = raw.strip()
            for name in ("state", "runs", "last exit code", "run interval"):
                prefix = name + " = "
                if line.startswith(prefix):
                    fields[name.replace(" ", "_")] = line[len(prefix):].strip()
        runs = int(fields.get("runs", "0")) if fields.get("runs", "0").isdigit() else 0
        interval_text = fields.get("run_interval", "").removesuffix(" seconds").strip()
        watcher = {
            "status": "VERIFIED LIVE" if runs > 0 else "NOT WORKING",
            "loaded": True,
            "state": fields.get("state", "unknown"),
            "runs_since_load": runs,
            "last_exit_code": fields.get("last_exit_code", "unknown"),
            "run_interval_seconds": int(interval_text)
            if interval_text.isdigit()
            else None,
        }
    skill_dir = Path(str(environ.get("NARRATIIVE_PRESENTATION_SKILL_DIR") or "")).expanduser()
    return {
        "gmail_inbox_watch": watcher,
        "presentation_runtime_dependency": {
            "status": "VERIFIED LIVE" if skill_dir.is_dir() else "NOT WORKING",
            "configured": bool(str(environ.get("NARRATIIVE_PRESENTATION_SKILL_DIR") or "").strip()),
            "configured_path_exists": skill_dir.is_dir(),
        },
    }


def _business_adapter_probes(dispatchers: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in BUSINESS_SURFACES:
        dispatcher = dispatchers.get(name)
        if dispatcher is None:
            result[name] = {"status": "NOT WORKING", "configured": False}
            continue
        probe = getattr(dispatcher, "probe", None)
        if not callable(probe):
            result[name] = {"status": "NOT TESTED", "configured": True, "reason": "no read-only probe"}
            continue
        try:
            evidence = probe()
        except Exception as exc:
            result[name] = {"status": "NOT WORKING", "configured": True, "error": _provider_error(exc)}
            continue
        result[name] = {
            "status": "VERIFIED LIVE",
            "configured": True,
            "source_id": str(evidence.get("source_id") or ""),
            "read_only": evidence.get("read_only") is True,
            "mutation_count": int(evidence.get("mutation_count") or 0),
            "validated_capabilities": list(evidence.get("validated_capabilities") or []),
        }
    return result


def _safe_read(
    dispatchers: Mapping[str, Any],
    *,
    action: str,
    surface: str,
    operation: str,
    target: Mapping[str, Any],
) -> dict[str, Any]:
    result = execute_payload(
        {
            "action": action,
            "surface": surface,
            "kind": "read",
            "operation": operation,
            "target": dict(target),
        },
        dispatchers,
    )
    evidence = result.get("evidence") if isinstance(result.get("evidence"), Mapping) else {}
    identifiers: list[str] = []
    for key in ("record_ids", "event_ids"):
        values = evidence.get(key)
        if isinstance(values, list):
            identifiers.extend(_redacted_identifier(item) for item in values[:5] if item)
    for key in ("message_id", "thread_id", "record_id", "file_id", "transcript_id"):
        if evidence.get(key):
            identifiers.append(_redacted_identifier(evidence[key]))
    counts = {
        key: int(evidence.get(key) or 0)
        for key in ("result_count", "busy_count")
        if evidence.get(key) is not None
    }
    return {
        "status": "VERIFIED LIVE" if result.get("ok") is True else "NOT WORKING",
        "runtime_status": str(result.get("status") or ""),
        "execution_truth": str(result.get("execution_truth") or ""),
        "source_id": str(evidence.get("source_id") or ""),
        "mutation_count": int(evidence.get("mutation_count") or 0),
        "counts": counts,
        "redacted_record_ids": identifiers,
        "error": str(result.get("error") or result.get("reason") or ""),
    }


def _journey_reads(dispatchers: Mapping[str, Any], audit_date: date) -> dict[str, Any]:
    marker = "ISSUE477-FICTIONAL-MARKER-ALPHA"
    return {
        "gmail": _safe_read(
            dispatchers,
            action=f"Search Gmail for fictional marker {marker}",
            surface="gmail",
            operation="search",
            target={"query": marker, "max_results": 5},
        ),
        "notion": _safe_read(
            dispatchers,
            action=f"Search Notion for fictional marker {marker}",
            surface="notion",
            operation="search",
            target={"query": marker, "max_results": 5},
        ),
        "fireflies": _safe_read(
            dispatchers,
            action="List at most one Fireflies transcript record without content",
            surface="fireflies",
            operation="list",
            target={"max_results": 1},
        ),
        "drive": _safe_read(
            dispatchers,
            action="List at most one Google Drive file metadata record",
            surface="drive",
            operation="list",
            target={"max_results": 1},
        ),
        "calendar": _safe_read(
            dispatchers,
            action="Read Google Calendar availability for the audit date",
            surface="calendar",
            operation="inspect",
            target={"start_date": audit_date.isoformat(), "end_date": audit_date.isoformat()},
        ),
        "n8n": _safe_read(
            dispatchers,
            action="Find the unified inbound lead workflow in n8n",
            surface="n8n",
            operation="search",
            target={"query": "Unified Inbound Lead Intake", "max_results": 5},
        ),
    }


def _telegram_probe(environ: Mapping[str, str]) -> dict[str, Any]:
    token = str(environ.get("TONY_TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        return {"status": "NOT WORKING", "configured": False}
    result: dict[str, Any] = {"configured": True, "mutation_count": 0}
    status, identity = _http_json(f"https://api.telegram.org/bot{token}/getMe")
    bot = identity.get("result") if isinstance(identity.get("result"), Mapping) else {}
    result["identity"] = {
        "ok": status == 200 and identity.get("ok") is True,
        "bot_id": _redacted_identifier(bot.get("id")),
        "is_bot": bot.get("is_bot") is True,
    }
    status, webhook_payload = _http_json(f"https://api.telegram.org/bot{token}/getWebhookInfo")
    webhook = webhook_payload.get("result") if isinstance(webhook_payload.get("result"), Mapping) else {}
    result["webhook"] = {
        "ok": status == 200 and webhook_payload.get("ok") is True,
        "configured": bool(webhook.get("url")),
        "pending_update_count": int(webhook.get("pending_update_count") or 0),
        "last_error_present": bool(webhook.get("last_error_message")),
    }
    result["status"] = "VERIFIED LIVE" if result["identity"]["ok"] and result["webhook"]["ok"] else "NOT WORKING"
    return result


def _activation_probe(environ: Mapping[str, str]) -> dict[str, Any]:
    configured = build_configured_media_adapters(environ)
    result: dict[str, Any] = {}
    for provider_name in ("meta", "tiktok", "google"):
        adapter = next((item for provider, item in configured.items() if provider.value == provider_name), None)
        if adapter is None:
            result[provider_name] = {"status": "NOT WORKING", "configured": False}
            continue
        row: dict[str, Any] = {"configured": True, "read_only": True, "mutation_count": 0}
        for operation in ("authenticate", "get_accounts", "get_permissions", "get_businesses", "get_campaigns"):
            if provider_name == "google" and operation in {"get_permissions", "get_businesses"}:
                row[operation] = {"status": "NOT TESTED", "reason": "adapter does not expose this provider operation"}
                continue
            try:
                value = getattr(adapter, operation)()
            except Exception as exc:
                row[operation] = {"status": "NOT WORKING", "error": _provider_error(exc)}
            else:
                row[operation] = {
                    "status": "VERIFIED LIVE",
                    "count": len(value) if isinstance(value, (list, tuple)) else None,
                }
        required = [row["authenticate"], row["get_accounts"], row["get_campaigns"]]
        row["status"] = "VERIFIED LIVE" if all(item.get("status") == "VERIFIED LIVE" for item in required) else "PARTIAL"
        result[provider_name] = row
    return result


def build_report(environ: Mapping[str, str], audit_date: date) -> dict[str, Any]:
    dispatchers = build_http_dispatchers(environ)
    return {
        "schema_version": 1,
        "issue": 477,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "classification_legend": [
            "VERIFIED LIVE",
            "VERIFIED SANDBOX",
            "SIMULATED",
            "NOT WORKING",
            "NOT TESTED",
        ],
        "safeguards": {
            "fictional_marker": "ISSUE477-FICTIONAL-MARKER-ALPHA",
            "external_writes": 0,
            "outreach_sent": False,
            "campaigns_published": False,
            "media_spend": False,
            "production_configuration_changed": False,
        },
        "service_health": _health_checks(),
        "runtime_observations": _runtime_observations(environ),
        "business_adapter_probes": _business_adapter_probes(dispatchers),
        "journey_safe_reads": _journey_reads(dispatchers, audit_date),
        "telegram": _telegram_probe(environ),
        "activation": _activation_probe(environ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Issue #477 read-only live integration evidence probes.")
    parser.add_argument("--audit-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(os.environ, args.audit_date)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    live_failures = [
        name for name, item in report["business_adapter_probes"].items()
        if item["status"] == "NOT WORKING"
    ]
    return 1 if live_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
