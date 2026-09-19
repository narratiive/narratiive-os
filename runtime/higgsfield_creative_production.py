from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import random
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError


class HiggsfieldConfigurationError(RuntimeError):
    pass


class HiggsfieldProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class HiggsfieldConfig:
    credential: str
    api_base: str = "https://api.higgsfield.ai"
    image_model: str = "marketing-studio/image"
    video_model: str = "bytedance/seedance-2.5/text-to-video"
    poll_timeout_seconds: float = 900.0
    max_download_bytes: int = 100 * 1024 * 1024

    def __post_init__(self) -> None:
        if not self.credential.strip() or ":" not in self.credential:
            raise HiggsfieldConfigurationError("Higgsfield key ID and secret are required")
        if not self.api_base.startswith("https://"):
            raise HiggsfieldConfigurationError("Higgsfield API base must use HTTPS")
        if self.poll_timeout_seconds <= 0 or self.max_download_bytes <= 0:
            raise HiggsfieldConfigurationError("Higgsfield time and size limits must be positive")


def higgsfield_credential(environ: Mapping[str, str]) -> str:
    combined = str(environ.get("HF_KEY") or environ.get("HF_CREDENTIALS") or "").strip()
    key_id = str(environ.get("HF_API_KEY_ID") or "").strip()
    secret = str(environ.get("HF_API_KEY_SECRET") or "").strip()
    if combined:
        return combined
    if key_id and secret:
        return f"{key_id}:{secret}"
    if key_id and ":" in key_id:
        return key_id
    return ""


class HiggsfieldCreativeProductionDispatcher:
    """Generate exact approved image/video assets and persist them to Google Drive."""

    _TERMINAL = {"completed", "failed", "nsfw", "canceled"}
    _SUPPORTED = {"image_generation", "short_form_video_production"}

    def __init__(
        self,
        config: HiggsfieldConfig,
        *,
        state_root: Path,
        drive_dispatcher: Callable[[dict[str, Any]], dict[str, Any]],
        opener: Callable[..., Any] = request.urlopen,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.state_root = Path(state_root).resolve()
        self.asset_root = self.state_root / "files"
        self.drive_dispatcher = drive_dispatcher
        self.opener = opener
        self.sleeper = sleeper
        self.clock = clock

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        context = _mapping(contract.get("workflow_context"))
        if context.get("workflow_id") != "creative_bible_to_asset_production":
            raise HiggsfieldProviderError("Higgsfield received an unsupported workflow")
        idempotency_key = _text(context.get("idempotency_key"))
        manifest = _mapping(contract.get("asset_manifest"))
        assets = manifest.get("assets")
        tasks = contract.get("production_tasks")
        specifications = contract.get("channel_asset_specifications")
        if not idempotency_key or not isinstance(assets, list) or not isinstance(tasks, list) or not isinstance(specifications, list):
            raise HiggsfieldProviderError("Higgsfield production contract is incomplete")
        tasks_by_job = {_text(item.get("job_id")): item for item in tasks if isinstance(item, Mapping)}
        specs_by_id = {_text(item.get("specification_id")): item for item in specifications if isinstance(item, Mapping)}
        manifest_checksum = _checksum(manifest)
        provider_scope = ":".join(
            _text(context.get(field))
            for field in ("workspace_id", "client_id", "run_id", "stage_id")
            if _text(context.get(field))
        ) or idempotency_key.rsplit(":", 1)[0]
        provider_scope = f"{provider_scope}:{manifest_checksum}"
        versions, receipts, request_ids = [], [], []
        for asset in assets:
            if not isinstance(asset, Mapping):
                raise HiggsfieldProviderError("Higgsfield manifest asset is invalid")
            job_id = _text(asset.get("production_job_id"))
            task = _mapping(tasks_by_job.get(job_id))
            specification = _mapping(specs_by_id.get(_text(asset.get("specification_id"))))
            capability = _text(task.get("required_capability"))
            if capability not in self._SUPPORTED:
                raise HiggsfieldProviderError(f"Higgsfield does not support production capability: {capability}")
            version, receipt = self._produce(asset, task, specification, manifest_checksum, provider_scope)
            versions.append(version)
            receipts.append(receipt)
            request_ids.append(_text(receipt.get("provider_request_id")))
        return {
            "asset_versions": versions,
            "production_receipts": receipts,
            "external_action_taken": True,
            "external_action_receipt": {
                "provider": "higgsfield",
                "provider_request_ids": request_ids,
                "asset_manifest_checksum": manifest_checksum,
                "drive_ingestion_verified": True,
            },
            "delivery_authorised": False,
            "publication_authorised": False,
            "media_spend_authorised": False,
        }

    def _produce(self, asset, task, specification, manifest_checksum, provider_scope):
        asset_id = _text(asset.get("asset_id"))
        job_id = _text(asset.get("production_job_id"))
        if not asset_id or not job_id:
            raise HiggsfieldProviderError("Higgsfield asset identity is incomplete")
        request_key = hashlib.sha256(f"{provider_scope}\0{asset_id}\0{job_id}".encode()).hexdigest()
        state_path = self.state_root / "requests" / f"{request_key}.json"
        state = self._read_state(state_path)
        capability = _text(task.get("required_capability"))
        model, payload = self._request(capability, specification)
        if state.get("state") == "submission_ambiguous":
            raise HiggsfieldProviderError("Higgsfield submission requires manual reconciliation before retry")
        if state.get("state") == "complete":
            return dict(state["asset_version"]), dict(state["receipt"])
        request_id, status_url = _text(state.get("request_id")), _text(state.get("status_url"))
        correlation_id = _text(state.get("correlation_id"))
        if not request_id or not status_url:
            try:
                submission, correlation_id = self._json_call(f"{self.config.api_base.rstrip('/')}/{model}", method="POST", body=payload)
            except (TimeoutError, URLError, OSError) as exc:
                self._write_state(state_path, {"state": "submission_ambiguous", "model": model})
                raise HiggsfieldProviderError("Higgsfield submission outcome is ambiguous") from exc
            request_id, status_url = _text(submission.get("request_id")), _text(submission.get("status_url"))
            if not request_id or not status_url:
                raise HiggsfieldProviderError("Higgsfield did not return request identity")
            self._write_state(state_path, {"state": "submitted", "request_id": request_id, "status_url": status_url, "correlation_id": correlation_id, "model": model})
        result = self._poll(status_url)
        if _text(result.get("status")) != "completed":
            raise HiggsfieldProviderError(f"Higgsfield generation ended in {_text(result.get('status')) or 'unknown'} state")
        output_url = self._output_url(result, capability)
        media, content_type = self._download(output_url)
        checksum = hashlib.sha256(media).hexdigest()
        extension = self._extension(content_type, specification, output_url)
        content_type = content_type or mimetypes.types_map.get(extension, "application/octet-stream")
        version_id = f"{asset_id}-v{int(asset.get('planned_version') or 1)}"
        local_path = self._persist_file(version_id, extension, media)
        drive = self.drive_dispatcher({
            "execution_mode": "approved_write",
            "approval_granted": True,
            "idempotency_key": f"higgsfield:{request_id}:{version_id}",
            "payload": {
                "kind": "creative_asset_version", "local_path": str(local_path),
                "filename": local_path.name, "mime_type": content_type, "checksum": checksum,
                "asset_id": asset_id, "asset_version_id": version_id,
                "production_job_id": job_id, "provider_request_id": request_id,
            },
            "target": {},
        })
        drive_uri = _text(drive.get("file_url") or drive.get("url"))
        if drive.get("verified") is not True or not drive_uri:
            raise HiggsfieldProviderError("Google Drive did not verify Higgsfield asset ingestion")
        version = {
            "asset_version_id": version_id, "asset_id": asset_id, "production_job_id": job_id,
            "file_checksum": checksum, "drive_uri": drive_uri,
            "source_manifest_checksum": manifest_checksum,
            "version_number": int(asset.get("planned_version") or 1), "status": "in_review",
            "approval_status": "pending", "human_review_required": True,
            "delivery_authorised": False, "publication_authorised": False,
        }
        receipt = {
            "asset_version_id": version_id, "provider": "higgsfield",
            "provider_request_id": request_id, "provider_receipt_id": request_id,
            "provider_correlation_id": correlation_id, "model": model, "status": "complete",
            "drive_file_id": _text(drive.get("file_id")),
        }
        self._write_state(state_path, {"state": "complete", "request_id": request_id, "status_url": status_url, "correlation_id": correlation_id, "model": model, "asset_version": version, "receipt": receipt})
        return version, receipt

    def _request(self, capability: str, specification: Mapping[str, Any]):
        direction = _mapping(specification.get("creative_direction"))
        prompt = ". ".join(_text(direction.get(field)) for field in ("visual_direction", "message", "role", "audience", "format_notes", "production_notes") if _text(direction.get(field)))
        if len(prompt) < 2:
            raise HiggsfieldProviderError("Higgsfield production prompt is missing")
        ratio = _normalise_ratio(_text(specification.get("aspect_ratio")))
        if capability == "short_form_video_production":
            duration = max(5, min(int(float(specification.get("duration_seconds") or 5)), 30))
            return self.config.video_model, {"prompt": prompt[:2048], "duration": duration, "resolution": "720p", "aspect_ratio": ratio, "bitrate_mode": "high", "output_format": "mp4", "generate_audio": True}
        return self.config.image_model, {"prompt": prompt[:2048], "quality": "high", "moderation": "auto", "resolution": "2k", "aspect_ratio": ratio, "enhance_prompt": False}

    def _poll(self, status_url: str):
        if not status_url.startswith(f"{self.config.api_base.rstrip('/')}/requests/"):
            raise HiggsfieldProviderError("Higgsfield returned an untrusted status URL")
        deadline, delay = self.clock() + self.config.poll_timeout_seconds, 2.0
        while self.clock() < deadline:
            try:
                result, _ = self._json_call(status_url)
            except HiggsfieldProviderError as exc:
                if any(marker in str(exc) for marker in ("credentials", "credits", "HTTP 404")):
                    raise
                self.sleeper(min(delay, 10.0)); delay = min(delay * 1.5, 10.0); continue
            except (TimeoutError, URLError, OSError):
                self.sleeper(min(delay, 10.0)); delay = min(delay * 1.5, 10.0); continue
            if _text(result.get("status")).casefold() in self._TERMINAL:
                return result
            self.sleeper(delay + random.uniform(0, 0.25)); delay = min(delay * 1.5, 10.0)
        raise HiggsfieldProviderError("Higgsfield generation timed out")

    def _json_call(self, url: str, *, method="GET", body=None):
        data = json.dumps(dict(body)).encode() if body is not None else None
        headers = {"Authorization": f"Key {self.config.credential}", "Accept": "application/json"}
        if body is not None: headers["Content-Type"] = "application/json"
        req = request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener(req, timeout=30) as response:
                raw = response.read(1_000_001)
                correlation = _text(getattr(response, "headers", {}).get("X-Correlation-ID"))
        except HTTPError as exc:
            if exc.code == 403: raise HiggsfieldProviderError("Higgsfield account has insufficient credits") from exc
            if exc.code == 401: raise HiggsfieldProviderError("Higgsfield credentials were rejected") from exc
            raise HiggsfieldProviderError(f"Higgsfield API returned HTTP {exc.code}") from exc
        if len(raw) > 1_000_000: raise HiggsfieldProviderError("Higgsfield response exceeded the size limit")
        try: payload = json.loads(raw.decode() or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise HiggsfieldProviderError("Higgsfield returned an invalid response") from exc
        if not isinstance(payload, dict): raise HiggsfieldProviderError("Higgsfield returned an invalid response")
        return payload, correlation

    def _download(self, url: str):
        if not url.startswith("https://"): raise HiggsfieldProviderError("Higgsfield returned an unsafe media URL")
        try:
            with self.opener(request.Request(url, headers={"Accept": "*/*"}), timeout=60) as response:
                data = response.read(self.config.max_download_bytes + 1)
                content_type = _text(getattr(response, "headers", {}).get("Content-Type")).split(";", 1)[0]
        except (HTTPError, URLError, TimeoutError, OSError) as exc: raise HiggsfieldProviderError("Higgsfield media download failed") from exc
        if not data or len(data) > self.config.max_download_bytes: raise HiggsfieldProviderError("Higgsfield media file is empty or too large")
        return data, content_type

    @staticmethod
    def _output_url(result, capability):
        if capability == "short_form_video_production": url = _text(_mapping(result.get("video")).get("url"))
        else:
            images = result.get("images")
            url = _text(images[0].get("url")) if isinstance(images, list) and images and isinstance(images[0], Mapping) else ""
        if not url: raise HiggsfieldProviderError("Higgsfield completed without a media URL")
        return url

    @staticmethod
    def _extension(content_type, specification, url):
        extension = mimetypes.guess_extension(content_type) or Path(url.split("?", 1)[0]).suffix or f".{_text(specification.get('file_format')).casefold()}"
        if extension == ".jpe": extension = ".jpg"
        if extension not in {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov"}: raise HiggsfieldProviderError("Higgsfield returned an unsupported media type")
        return extension

    def _persist_file(self, version_id, extension, data):
        if Path(version_id).name != version_id or not re.fullmatch(r"[A-Za-z0-9._-]+", version_id):
            raise HiggsfieldProviderError("Higgsfield asset version identity is unsafe")
        self.asset_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path, temporary = self.asset_root / f"{version_id}{extension}", self.asset_root / f"{version_id}{extension}.tmp"
        temporary.write_bytes(data); os.chmod(temporary, 0o600); temporary.replace(path)
        return path

    @staticmethod
    def _read_state(path):
        if not path.is_file(): return {}
        try: value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise HiggsfieldProviderError("Higgsfield request state is unreadable") from exc
        if not isinstance(value, dict): raise HiggsfieldProviderError("Higgsfield request state is invalid")
        return value

    @staticmethod
    def _write_state(path, value):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(dict(value), indent=2, sort_keys=True), encoding="utf-8")
        os.chmod(temporary, 0o600); temporary.replace(path)


def _mapping(value): return value if isinstance(value, Mapping) else {}
def _text(value): return str(value or "").strip()
def _checksum(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
def _normalise_ratio(value):
    return {"1080:1920": "9:16", "1920:1080": "16:9", "1200:1500": "4:5"}.get(value, value if value in {"1:1", "9:16", "16:9", "4:5", "5:4", "3:4", "4:3"} else "1:1")
