"""Fieldwork presentation contract shared by preparation, review and approval."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping
from runtime.fieldwork_proposal import TEMPLATE, TEMPLATE_VERSION, validate_inputs

PROPOSAL_WORKFLOW = 'discovery_evidence_to_growth_sprint_proposal'


def proposal_inputs(output: Mapping[str, Any]) -> dict[str, Any]:
    data = validate_inputs(output.get('fieldwork_proposal'))
    if output.get('external_action_taken') is not False:
        raise ValueError('Fieldwork preparation must have no external action')
    commercial = output.get('commercial_proposal_inputs')
    if not isinstance(commercial, Mapping) or commercial.get('timeline') != '7 working days':
        raise ValueError('Seven-working-day commercial scope required')
    if commercial.get('proposed_fee') != data['proposed_fee']:
        raise ValueError('Internal and visible proposed fee must match exactly')
    return data


def email_draft(output: Mapping[str, Any], checksum: str, *, source_checksum: str) -> dict[str, Any]:
    data = proposal_inputs(output)
    body = str(output.get('draft_client_communication') or '').strip()
    if not body or any(term in body.casefold() for term in ('growth sprint', 'blueprint lite')):
        raise ValueError('Fieldwork email draft required; legacy names prohibited')
    draft = dict(subject=f"{data['client_name']} — Fieldwork proposal", body=body,
        intended_client=data['client_name'], recipient_email=None, status='draft_not_authorised',
        pdf_sha256=checksum, source_artifact_checksum=source_checksum,
        proposed_fee=data['proposed_fee'], template_version=TEMPLATE_VERSION,
        fictional=data['fictional'], send_authorised=False)
    draft['draft_sha256'] = hashlib.sha256(json.dumps(draft,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return draft


def preparation_guidance() -> str:
    shape = json.loads((TEMPLATE/'origin-fictional.json').read_text())
    return (' Use Fieldwork in all new client copy. Keep the detailed internal brief separate from '
        'fieldwork_proposal, the complete structured two-page renderer input. Seven working days, '
        'one exact proposed GBP fee excluding VAT, approved=false. Copy and five distinct image '
        'records must be tailored to the current client and sourced evidence. Never invent discovery. '
        'Fictional examples must disclose absent discovery and illustrative model assumptions. '
        'commercial_proposal_inputs.timeline must be "7 working days" and its proposed_fee must '
        'exactly equal fieldwork_proposal.proposed_fee. draft_client_communication is a personalised '
        'Fieldwork email draft, not a claim of sending. If fieldwork_revision_inputs is supplied, '
        'preserve that exact approved-reference candidate input without rewriting its copy, figures '
        'or image records. Otherwise use this shape as a schema example only; do not reuse Origin '
        'copy, sources, identities or imagery for another client. Workspace/client IDs must match '
        'workflow_context. Supported local assets are relative to templates/fieldwork/v4; missing '
        'client-specific imagery or evidence is a blocker, not permission to fabricate. '
        + json.dumps(shape,ensure_ascii=False))
