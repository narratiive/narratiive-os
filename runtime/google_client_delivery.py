from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any
from urllib import parse


class GoogleClientDeliveryError(RuntimeError):
    pass


class GoogleClientDeliveryDispatcher:
    """Copy one approved package into client Drive and then notify by email."""

    def __init__(
        self,
        *,
        drive_dispatcher: Callable[[dict[str, Any]], dict[str, Any]],
        gmail_dispatcher: Callable[[dict[str, Any]], dict[str, Any]],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.drive_dispatcher = drive_dispatcher
        self.gmail_dispatcher = gmail_dispatcher
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        context = _mapping(contract.get("workflow_context"))
        if context.get("workflow_id") != "asset_review_to_delivery_preparation":
            raise GoogleClientDeliveryError("Google client delivery received an unsupported workflow")
        package = _mapping(contract.get("delivery_package"))
        package_id = _text(package.get("delivery_package_id"))
        package_checksum = _text(package.get("checksum"))
        assets = package.get("assets")
        requirements = _mapping(package.get("delivery_requirements"))
        if not package_id or not re.fullmatch(r"[0-9a-f]{64}", package_checksum):
            raise GoogleClientDeliveryError("Google client delivery package identity is invalid")
        if not isinstance(assets, list) or not assets:
            raise GoogleClientDeliveryError("Google client delivery package contains no assets")

        folder_id = _safe_google_id(
            requirements.get("client_drive_folder_id")
            or requirements.get("drive_folder_id")
            or requirements.get("destination_folder_id"),
            "client Drive folder",
        )
        recipient = _recipient(
            requirements.get("notification_email")
            or requirements.get("recipient_email")
            or requirements.get("client_email")
        )
        copied_assets = []
        delivered_ids = []
        for raw_asset in assets:
            asset = _mapping(raw_asset)
            version_id = _text(asset.get("asset_version_id"))
            checksum = _text(asset.get("file_checksum"))
            source_file_id = _drive_file_id(_text(asset.get("drive_uri")))
            if not version_id or not re.fullmatch(r"[0-9a-f]{64}", checksum):
                raise GoogleClientDeliveryError("Google client delivery asset identity is invalid")
            copied = self.drive_dispatcher(
                {
                    "execution_mode": "approved_write",
                    "approval_granted": True,
                    "approval_scope": "exact_client_asset_delivery",
                    "idempotency_key": f"{package_checksum}:{version_id}:drive-copy",
                    "payload": {
                        "kind": "client_delivery_asset_copy",
                        "source_file_id": source_file_id,
                        "destination_folder_id": folder_id,
                        "asset_version_id": version_id,
                        "checksum": checksum,
                    },
                    "target": {"drive_folder_id": folder_id},
                }
            )
            copied_id = _text(copied.get("file_id"))
            copied_url = _text(copied.get("file_url") or copied.get("url"))
            if copied.get("verified") is not True or not copied_id or not copied_url:
                raise GoogleClientDeliveryError("Google Drive did not verify the client asset copy")
            copied_assets.append(
                {
                    "asset_version_id": version_id,
                    "file_id": copied_id,
                    "file_url": copied_url,
                    "checksum": checksum,
                }
            )
            delivered_ids.append(version_id)

        identity = _mapping(package.get("campaign_identity"))
        campaign_name = _text(identity.get("campaign_name") or identity.get("name") or identity.get("campaign_id"))
        label = campaign_name or "your approved creative assets"
        folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
        links = "\n".join(f"- {item['asset_version_id']}: {item['file_url']}" for item in copied_assets)
        email = self.gmail_dispatcher(
            {
                "execution_mode": "approved_write",
                "approval_granted": True,
                "approval_scope": "exact_client_asset_delivery",
                "idempotency_key": f"{package_checksum}:delivery-notification",
                "payload": {
                    "kind": "client_asset_delivery_notification",
                    "recipient_email": recipient,
                    "subject": f"Narratiive delivery: {label}",
                    "body": (
                        f"Your approved Narratiive assets for {label} are ready.\n\n"
                        f"Client Drive folder: {folder_url}\n\n"
                        f"Delivered versions:\n{links}\n"
                    ),
                },
                "target": {"recipient_email": recipient},
            }
        )
        message_id = _text(email.get("message_id"))
        if email.get("verified") is not True or email.get("sent") is not True or not message_id:
            raise GoogleClientDeliveryError("Gmail did not verify the client notification")

        delivered_at = self.clock().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        receipt_id = "delivery-" + hashlib.sha256(
            f"{package_checksum}\0{folder_id}\0{recipient}".encode("utf-8")
        ).hexdigest()[:24]
        return {
            "verified_delivery_evidence": {
                "delivery_package_id": package_id,
                "delivery_package_checksum": package_checksum,
                "destination": folder_url,
                "destination_folder_id": folder_id,
                "notification_recipient": recipient,
                "notification_message_id": message_id,
                "delivered_at": delivered_at,
                "delivered_asset_version_ids": delivered_ids,
                "delivered_assets": copied_assets,
            },
            "delivery_receipt": {
                "receipt_id": receipt_id,
                "delivery_package_checksum": package_checksum,
                "status": "delivered",
                "drive_folder_id": folder_id,
                "gmail_message_id": message_id,
            },
            "external_action_receipt": {
                "receipt_id": receipt_id,
                "provider": "google_drive_gmail",
                "drive_file_ids": [item["file_id"] for item in copied_assets],
                "gmail_message_id": message_id,
            },
            "external_action_taken": True,
            "delivery_authorised": True,
            "publication_authorised": False,
            "media_spend_authorised": False,
        }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_google_id(value: Any, label: str) -> str:
    identifier = _text(value)
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,200}", identifier):
        raise GoogleClientDeliveryError(f"Google client delivery requires an exact {label} ID")
    return identifier


def _recipient(value: Any) -> str:
    recipient = _text(value)
    if (
        not re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+", recipient)
        or any(marker in recipient for marker in ("\r", "\n"))
    ):
        raise GoogleClientDeliveryError("Google client delivery requires one exact notification email")
    return recipient


def _drive_file_id(uri: str) -> str:
    try:
        parsed = parse.urlparse(uri)
    except ValueError as exc:
        raise GoogleClientDeliveryError("Google client delivery asset Drive URI is invalid") from exc
    if parsed.scheme != "https" or parsed.hostname not in {"drive.google.com", "docs.google.com"}:
        raise GoogleClientDeliveryError("Google client delivery asset must use a trusted Drive URI")
    query_id = parse.parse_qs(parsed.query).get("id", [""])[0]
    parts = [part for part in parsed.path.split("/") if part]
    path_id = parts[parts.index("d") + 1] if "d" in parts and parts.index("d") + 1 < len(parts) else ""
    return _safe_google_id(query_id or path_id, "source Drive file")
