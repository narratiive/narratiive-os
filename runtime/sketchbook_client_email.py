from __future__ import annotations

import base64
import hashlib
import html
import ipaddress
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from runtime.serialization import artifact_to_dict
from runtime.tony_workflow_runtime import _workflow_value_checksum


MAX_FILE_BYTES = 5_000_000
TEMPLATE_ID = "narratiive-sketchbook-client-delivery-v1"
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_REQUIRED_SUMMARY_FIELDS = (
    "first_name",
    "client_name",
    "recipient_email",
    "approved_creative_idea",
    "approved_reason_for_audience",
    "approved_next_step",
    "sender_name",
    "sender_identity_evidence_ref",
)


class SketchbookClientEmailError(ValueError):
    pass


class SketchbookClientEmailService:
    """Adopt an exact Sketchbook presentation and prepare an unsent client draft.

    This is deliberately separate from document handback: it attaches a complete
    presentation package to an already approved Creative Bible run without
    reopening or completing that run. It exposes no client-send operation.
    """

    def __init__(self, runtime, dispatchers: Mapping[str, Any] | None = None) -> None:
        self.runtime = runtime
        self.dispatchers = dict(dispatchers or {})

    def register_preview(
        self,
        state,
        inputs: Mapping[str, Any],
        *,
        principal: str,
    ) -> dict[str, Any]:
        state = self.runtime.runs.load_run(state.run_id)
        self._assert_eligible_state(state, inputs, principal)
        version = _required_text(inputs, "version")
        title = _required_text(inputs, "title")
        summary = self._validated_summary(inputs.get("client_summary"))
        release = self._validated_release(inputs.get("release_conditions"))
        files = self._persist_files(state, inputs.get("files"))
        qa = self._validated_qa(inputs.get("quality_assurance"), files)
        creative_bible_checksum = self._approved_creative_bible_checksum(state)
        supplied_bible_checksum = _required_text(inputs, "approved_creative_bible_checksum")
        if supplied_bible_checksum != creative_bible_checksum:
            raise SketchbookClientEmailError(
                "Sketchbook package does not match the approved Creative Director's Bible"
            )

        booking_link = self._verified_booking_link(inputs)
        review_link = self._verified_review_link(inputs, files) if release["satisfied"] else ""
        message = render_sketchbook_email(summary, booking_link=booking_link, review_link=review_link)
        manifest = {
            "kind": "sketchbook_client_presentation_candidate",
            "template_id": TEMPLATE_ID,
            "workspace_id": state.workspace_id,
            "client_id": state.client_id,
            "run_id": state.run_id,
            "title": title,
            "version": version,
            "real_client": inputs.get("real_client") is True,
            "approved_creative_bible_checksum": creative_bible_checksum,
            "client_summary": summary,
            "quality_assurance": qa,
            "release_conditions": release,
            "files": files,
            "draft_attachment_identities": [
                {
                    "role": item["role"],
                    "filename": item["filename"],
                    "sha256": item["sha256"],
                }
                for item in files
                if item["role"] in {"review_pdf", "creative_system_pdf"}
            ],
            "message": message,
            "client_send_authorised": False,
            "production_authorised": False,
            "payment_authorised": False,
        }
        candidate_checksum = _workflow_value_checksum(manifest)
        candidate_id = f"sketchbook-email-{candidate_checksum[:24]}"
        action_digest = _action_digest(candidate_id, candidate_checksum, manifest)
        manifest["candidate_id"] = candidate_id
        manifest["candidate_checksum"] = candidate_checksum
        manifest["action_digest"] = action_digest
        manifest["approval_status"] = "pending"
        manifest["send_blockers"] = self._send_blockers(manifest)

        key = f"sketchbook_email:{candidate_id}"
        existing = state.input_payload.get(key)
        if existing is not None:
            if not isinstance(existing, Mapping) or existing.get("candidate_checksum") != candidate_checksum:
                raise SketchbookClientEmailError("immutable Sketchbook candidate identity collision")
            return dict(existing)

        stage_id = state.stages[-1].stage_id
        artifact = self.runtime.coordinator.artifacts.persist_external_candidate(
            state,
            stage_id,
            manifest,
            candidate_id,
        )
        record = {**manifest, "artifact": artifact_to_dict(artifact)}
        self.runtime.runs.merge_inputs(state.run_id, {key: record})
        return record

    def prepare_draft(
        self,
        state,
        *,
        candidate_id: str,
        action_digest: str,
        approver: str,
        rationale: str,
    ) -> dict[str, Any]:
        state = self.runtime.runs.load_run(state.run_id)
        record = state.input_payload.get(f"sketchbook_email:{candidate_id.strip()}")
        if not isinstance(record, Mapping):
            raise SketchbookClientEmailError("exact registered Sketchbook email preview required")
        expected_digest = _action_digest(
            str(record.get("candidate_id") or ""),
            str(record.get("candidate_checksum") or ""),
            record,
        )
        if not action_digest.strip() or not _constant_time_equal(action_digest, expected_digest):
            raise SketchbookClientEmailError("Sketchbook email action digest is stale or incorrect")
        self._verify_candidate_files(record)
        self.runtime.runs.record_sketchbook_presentation_approval(
            state.run_id,
            approver=approver,
            rationale=rationale,
            candidate_id=str(record["candidate_id"]),
            candidate_checksum=str(record["candidate_checksum"]),
            action_digest=expected_digest,
        )

        key = f"sketchbook-draft:{expected_digest}"
        refreshed = self.runtime.runs.load_run(state.run_id)
        prior = next(
            (
                item.get("receipt")
                for item in refreshed.external_action_receipts
                if item.get("idempotency_key") == key and isinstance(item.get("receipt"), Mapping)
            ),
            None,
        )
        if prior is not None:
            return {**dict(prior), "duplicate_suppressed": True}
        gmail = self.dispatchers.get("Gmail")
        if gmail is None:
            raise SketchbookClientEmailError("Gmail adapter unavailable; exact approval is recorded but no draft is claimed")

        attachments = []
        for item in record["files"]:
            if item["role"] not in {"review_pdf", "creative_system_pdf"}:
                continue
            path = Path(str(item["location"]))
            attachments.append(
                {
                    "filename": item["filename"],
                    "mime_type": item["mime_type"],
                    "content_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
                }
            )
        message = record["message"]
        contract = {
            "execution_mode": "approved_write",
            "approval_granted": True,
            "operation": "create_draft",
            "idempotency_key": key,
            "payload": {
                "kind": "sketchbook_client_delivery_draft",
                "recipient_email": record["client_summary"]["recipient_email"],
                "subject": message["subject"],
                "body": message["plain_text"],
                "html_body": message["html"],
                "attachments": attachments,
            },
        }
        receipt = gmail(contract)
        if (
            not isinstance(receipt, Mapping)
            or receipt.get("verified") is not True
            or receipt.get("sent") is not False
            or not str(receipt.get("draft_id") or "").strip()
        ):
            raise SketchbookClientEmailError("unsent Gmail draft was not verified")
        recorded = {
            **dict(receipt),
            "kind": "sketchbook_client_delivery_draft",
            "candidate_id": record["candidate_id"],
            "candidate_checksum": record["candidate_checksum"],
            "action_digest": expected_digest,
            "recipient": record["client_summary"]["recipient_email"],
            "subject": message["subject"],
            "plain_text_sha256": _sha256_text(message["plain_text"]),
            "html_sha256": _sha256_text(message["html"]),
            "attachment_identities": [
                {
                    "role": item["role"],
                    "filename": item["filename"],
                    "sha256": item["sha256"],
                }
                for item in record["files"]
                if item["role"] in {"review_pdf", "creative_system_pdf"}
            ],
            "send_authorised": False,
            "client_send_boundary_available": False,
            "release_conditions_satisfied": record["release_conditions"]["satisfied"],
            "external_action_taken": True,
        }
        self.runtime.runs.record_external_action(
            state.run_id,
            idempotency_key=key,
            receipt=recorded,
        )
        return recorded

    @staticmethod
    def _assert_eligible_state(state, inputs: Mapping[str, Any], principal: str) -> None:
        if not principal.strip():
            raise SketchbookClientEmailError("authenticated principal required")
        if inputs.get("workspace_id") != state.workspace_id or inputs.get("client_id") != state.client_id:
            raise SketchbookClientEmailError("exact workspace/client binding required")
        if state.workflow_id != "campaign_world_to_creative_bible":
            raise SketchbookClientEmailError("Sketchbook presentation must attach to the Creative Bible workflow")
        if state.status.value != "complete" or state.approval_status != "approved":
            raise SketchbookClientEmailError("Sketchbook presentation requires the completed approved Creative Bible run")

    @staticmethod
    def _approved_creative_bible_checksum(state) -> str:
        decision = next(
            (
                item
                for item in reversed(state.approval_history)
                if item.get("decision") == "creative_bible_approval"
                and item.get("human_approval") is not False
            ),
            None,
        )
        checksum = str((decision or {}).get("creative_bible_checksum") or "").strip()
        if not checksum:
            raise SketchbookClientEmailError("Matt's exact Creative Bible approval is missing")
        return checksum

    def _persist_files(self, state, raw_files: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_files, list):
            raise SketchbookClientEmailError("Sketchbook package files must be a list")
        allowed = {
            "review_pdf": ("application/pdf", ".pdf", b"%PDF-"),
            "editable_source": (
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                ".pptx",
                b"PK",
            ),
            "creative_system_pdf": ("application/pdf", ".pdf", b"%PDF-"),
        }
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for raw in raw_files:
            if not isinstance(raw, Mapping):
                raise SketchbookClientEmailError("Sketchbook file entry must be an object")
            role = str(raw.get("role") or "").strip()
            if role not in allowed or role in seen:
                raise SketchbookClientEmailError("invalid or duplicate Sketchbook file role")
            seen.add(role)
            filename = str(raw.get("filename") or "").strip()
            mime_type, suffix, signature = allowed[role]
            if Path(filename).name != filename or not filename.casefold().endswith(suffix):
                raise SketchbookClientEmailError(f"{role} filename is invalid")
            try:
                data = base64.b64decode(str(raw.get("content_base64") or ""), validate=True)
            except (TypeError, ValueError) as exc:
                raise SketchbookClientEmailError(f"{role} content is not valid base64") from exc
            if not data or len(data) > MAX_FILE_BYTES or not data.startswith(signature):
                raise SketchbookClientEmailError(f"{role} is empty, oversized or not the declared document type")
            checksum = hashlib.sha256(data).hexdigest()
            root = self.runtime.coordinator.artifacts.root.resolve()
            directory = root / "external-files" / checksum
            directory.mkdir(parents=True, exist_ok=True)
            directory.resolve().relative_to(root)
            target = directory / filename
            if target.is_symlink():
                raise SketchbookClientEmailError("document symlinks are not accepted")
            if target.exists() and target.read_bytes() != data:
                raise SketchbookClientEmailError("immutable Sketchbook file collision")
            if not target.exists():
                with target.open("xb") as handle:
                    handle.write(data)
            result.append(
                {
                    "role": role,
                    "filename": filename,
                    "mime_type": mime_type,
                    "sha256": checksum,
                    "size": len(data),
                    "location": str(target),
                }
            )
        if not {"review_pdf", "editable_source"}.issubset(seen):
            raise SketchbookClientEmailError("Sketchbook requires both an exact review PDF and native editable PPTX")
        return result

    @staticmethod
    def _validated_summary(value: Any) -> dict[str, str]:
        if not isinstance(value, Mapping):
            raise SketchbookClientEmailError("approved client summary is required")
        result = {field: _required_text(value, field) for field in _REQUIRED_SUMMARY_FIELDS}
        if not _EMAIL_PATTERN.fullmatch(result["recipient_email"]):
            raise SketchbookClientEmailError("verified intended client recipient is invalid")
        if value.get("recipient_verified") is not True or not str(value.get("recipient_evidence_ref") or "").strip():
            raise SketchbookClientEmailError("verified intended client recipient evidence is required")
        result["recipient_evidence_ref"] = str(value["recipient_evidence_ref"]).strip()
        if any("{{" in item or "}}" in item for item in result.values()):
            raise SketchbookClientEmailError("client summary contains unresolved variables")
        return result

    @staticmethod
    def _validated_release(value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            return {"status": "unknown", "evidence_ref": "", "satisfied": False}
        status = str(value.get("status") or "unknown").strip().casefold()
        if status not in {"satisfied", "not_required", "unknown", "blocked"}:
            raise SketchbookClientEmailError("unsupported release-condition status")
        evidence_ref = str(value.get("evidence_ref") or "").strip()
        satisfied = status in {"satisfied", "not_required"} and bool(evidence_ref)
        return {"status": status, "evidence_ref": evidence_ref, "satisfied": satisfied}

    @staticmethod
    def _verified_booking_link(inputs: Mapping[str, Any]) -> str:
        link = _optional_public_url(inputs.get("booking_link"), "booking link")
        if not link:
            return ""
        evidence = inputs.get("booking_link_evidence")
        if (
            not isinstance(evidence, Mapping)
            or evidence.get("verified") is not True
            or not str(evidence.get("evidence_ref") or "").strip()
        ):
            raise SketchbookClientEmailError("booking link requires verified evidence")
        return link

    @staticmethod
    def _verified_review_link(inputs: Mapping[str, Any], files: list[dict[str, Any]]) -> str:
        link = _optional_public_url(inputs.get("review_link"), "review link")
        if not link:
            return ""
        evidence = inputs.get("review_link_evidence")
        review_pdf = next(item for item in files if item["role"] == "review_pdf")
        if (
            not isinstance(evidence, Mapping)
            or evidence.get("permission_verified") is not True
            or evidence.get("file_sha256") != review_pdf["sha256"]
            or not str(evidence.get("evidence_ref") or "").strip()
        ):
            raise SketchbookClientEmailError(
                "review link requires permission-checked exact-version evidence"
            )
        return link

    @staticmethod
    def _validated_qa(value: Any, files: list[dict[str, Any]]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise SketchbookClientEmailError("Sketchbook evidence and visual-QA bundle is required")
        by_role = {item["role"]: item for item in files}
        required_true = ("visual_qa_passed", "overflow_checked", "legibility_checked")
        if value.get("status") != "passed" or any(value.get(field) is not True for field in required_true):
            raise SketchbookClientEmailError("Sketchbook visual QA has not passed")
        if value.get("review_pdf_sha256") != by_role["review_pdf"]["sha256"]:
            raise SketchbookClientEmailError("Sketchbook QA does not match the review PDF")
        if value.get("editable_source_sha256") != by_role["editable_source"]["sha256"]:
            raise SketchbookClientEmailError("Sketchbook QA does not match the editable source")
        evidence = value.get("evidence_lineage")
        if not isinstance(evidence, list) or not evidence or any(not str(item).strip() for item in evidence):
            raise SketchbookClientEmailError("Sketchbook QA requires evidence lineage")
        page_count = value.get("page_count")
        if not isinstance(page_count, int) or page_count < 1:
            raise SketchbookClientEmailError("Sketchbook QA requires a valid page count")
        return {
            "status": "passed",
            "visual_qa_passed": True,
            "overflow_checked": True,
            "legibility_checked": True,
            "page_count": page_count,
            "review_pdf_sha256": by_role["review_pdf"]["sha256"],
            "editable_source_sha256": by_role["editable_source"]["sha256"],
            "evidence_lineage": [str(item).strip() for item in evidence],
        }

    @staticmethod
    def _verify_candidate_files(record: Mapping[str, Any]) -> None:
        files = record.get("files")
        if not isinstance(files, list):
            raise SketchbookClientEmailError("registered Sketchbook files are missing")
        for item in files:
            path = Path(str(item.get("location") or ""))
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item.get("sha256"):
                raise SketchbookClientEmailError("approved Sketchbook file changed after preview")

    @staticmethod
    def _send_blockers(record: Mapping[str, Any]) -> list[str]:
        blockers = [
            "A supported Sketchbook client-send operation is not implemented.",
            "Separate exact-message approval is required before client delivery.",
        ]
        if not record["release_conditions"]["satisfied"]:
            blockers.append("Commercial release conditions are unknown or unsatisfied; protected links remain withheld.")
        if record.get("real_client") is True:
            blockers.append("Real-client sending is disabled by this implementation scope.")
        return blockers


def render_sketchbook_email(
    summary: Mapping[str, str],
    *,
    booking_link: str = "",
    review_link: str = "",
) -> dict[str, str]:
    subject = f"{summary['client_name']}: your story is coming to life"
    invitation = (
        f"Choose a time to explore your Sketchbook: {booking_link}"
        if booking_link
        else "Reply to this email and we'll find a time to explore your Sketchbook together."
    )
    review_line = f"View your Sketchbook: {review_link}" if review_link else ""
    paragraphs = [
        f"Hi {summary['first_name']},",
        "This is the part we've been looking forward to showing you.",
        (
            "Your Sketchbook takes the direction we explored in Fieldwork and makes it visible: "
            f"the imagery, language and design that can bring {summary['client_name']}'s story to life."
        ),
        (
            f"We're particularly excited about {summary['approved_creative_idea']}. "
            f"{summary['approved_reason_for_audience']}"
        ),
        (
            "We'd love to walk you through the thinking, show you how the ideas connect and hear "
            "what feels most exciting to you."
        ),
        invitation,
        review_line,
        "If none of the available times work, just reply and we'll find one together." if booking_link else "",
        (
            "From here, we can agree which direction to develop and the production plan that will take it "
            f"into the world. {summary['approved_next_step']} Scope and investment will be agreed before production begins."
        ),
        "We're looking forward to exploring what comes next with you.",
        summary["sender_name"],
    ]
    plain = "\n\n".join(item for item in paragraphs if item)
    template = (Path(__file__).with_name("email_templates") / f"{TEMPLATE_ID}.html").read_text(encoding="utf-8")
    cta = (
        f'<a href="{html.escape(booking_link, quote=True)}" style="display:inline-block;background:#ef6a3a;color:#ffffff;text-decoration:none;font-size:16px;font-weight:700;line-height:1.2;padding:15px 22px;border-radius:2px;">Choose a time to explore your Sketchbook</a>'
        if booking_link
        else '<p style="margin:0;padding:18px 20px;background:#eadfcb;color:#10233f;font-size:16px;line-height:1.55;"><strong>Reply to this email</strong> and we\'ll find a time to explore your Sketchbook together.</p>'
    )
    secondary = (
        f'<p style="margin:0 0 24px;font-size:16px;"><a href="{html.escape(review_link, quote=True)}" style="color:#10233f;text-decoration:underline;">View your Sketchbook</a></p>'
        if review_link
        else ""
    )
    booking_fallback = (
        '<p style="margin:0 0 24px;font-size:16px;line-height:1.6;">If none of the available times work, just reply and we\'ll find one together.</p>'
        if booking_link
        else ""
    )
    substitutions = {
        "SUBJECT": subject,
        "FIRST_NAME": summary["first_name"],
        "CLIENT_NAME": summary["client_name"],
        "CREATIVE_IDEA": summary["approved_creative_idea"],
        "AUDIENCE_REASON": summary["approved_reason_for_audience"],
        "NEXT_STEP": summary["approved_next_step"],
        "SENDER_NAME": summary["sender_name"],
    }
    rendered = template
    for key, value in substitutions.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", html.escape(value))
    rendered = (
        rendered.replace("{{PRIMARY_CTA}}", cta)
        .replace("{{SECONDARY_LINK}}", secondary)
        .replace("{{BOOKING_FALLBACK}}", booking_fallback)
    )
    if "{{" in rendered or "}}" in rendered:
        raise SketchbookClientEmailError("email template contains unresolved variables")
    return {"subject": subject, "plain_text": plain, "html": rendered}


def _action_digest(candidate_id: str, candidate_checksum: str, record: Mapping[str, Any]) -> str:
    message = record.get("message") or {}
    files = record.get("files") or []
    material = {
        "candidate_id": candidate_id,
        "candidate_checksum": candidate_checksum,
        "recipient": (record.get("client_summary") or {}).get("recipient_email"),
        "subject": message.get("subject"),
        "plain_text_sha256": _sha256_text(str(message.get("plain_text") or "")),
        "html_sha256": _sha256_text(str(message.get("html") or "")),
        "attachments": [
            {"role": item.get("role"), "filename": item.get("filename"), "sha256": item.get("sha256")}
            for item in files
            if item.get("role") in {"review_pdf", "creative_system_pdf"}
        ],
        "release_conditions": record.get("release_conditions"),
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _required_text(value: Mapping[str, Any], field: str) -> str:
    text = str(value.get(field) or "").strip()
    if not text:
        raise SketchbookClientEmailError(f"{field} is required")
    return text


def _optional_public_url(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise SketchbookClientEmailError(f"{label} must be a public HTTPS URL")
    host = parsed.hostname.casefold()
    if host == "localhost" or host.endswith(".local"):
        raise SketchbookClientEmailError(f"{label} must be a public HTTPS URL")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise SketchbookClientEmailError(f"{label} must be a public HTTPS URL")
    return text


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _constant_time_equal(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left.strip(), right.strip())
