"""External document candidates using existing immutable storage/manual recovery.

No approval, stage completion, client send or publication occurs on registration.
"""
import base64
import hashlib
import json
from pathlib import Path
from urllib import request, parse
from runtime.serialization import artifact_to_dict
from runtime.workflow_mission_control import workflow_state_name
from runtime.tony_workflow_runtime import _workflow_value_checksum

RAVE_REFERENCE = 'https://drive.google.com/file/d/1ciJ2-Y8O0MIS5DAIe_tuoS3OXbIKUx--/view'
FIELDWORK_SPEC = 'https://docs.google.com/document/d/1KmY6uMSbdhGbl730bdXOPJh53nfhYjve6AVzexkXM1I/edit'
MAX_BYTES = 5_000_000


class DocumentHandbackService:
    def __init__(self, runtime, dispatchers):
        self.runtime = runtime
        self.dispatchers = dispatchers or {}

    def brief(self, state):
        result = {'client': state.client_id, 'client_name': workflow_state_name(state), 'engagement': state.run_id, 'workflow': state.workflow_id,
            'commercial_purpose': 'Fieldwork: find the growth audience, build the advantage, show the way to growth.' if state.workflow_id == 'growth_blueprint_deliverable_production' else 'Produce the current stage deliverable without changing approved upstream strategy.',
            'strategy_from_engagement': state.input_payload.get('quality_accepted_growth_blueprint') or state.input_payload.get('approved_growth_blueprint') or state.input_payload.get('approved_strategy_thesis'),
            'source_register': state.input_payload.get('source_register'),
            'required_outputs': list(state.stage(state.current_stage_id).expected_outputs) if state.current_stage_id else [],
            'strategy_identity': state.input_payload.get('blueprint_identity'),
            'evidence': state.input_payload.get('evidence_lineage', []),
            'reference': FIELDWORK_SPEC if state.workflow_id == 'growth_blueprint_deliverable_production' else None,
            'methodology_reference': RAVE_REFERENCE if state.workflow_id == 'growth_blueprint_deliverable_production' else None,
            'constraints': state.input_payload.get('production_constraints', []),
            'deadline': state.input_payload.get('agreed_deadline') or 'Not supplied; agree with Matt.', 'quality': 'Use the stage contract and source evidence; upload is not quality acceptance.',
            'return_to': 'Register against this exact engagement with producer, version, PDF and complete stage-output bundle. Then Matt reviews the exact candidate before manual recovery.',
            'automation': 'No specialist generation invoked.'}
        if state.workflow_id == 'growth_blueprint_deliverable_production':
            # Exact requested record only. Keep full evidence and identities in the
            # existing detailed result, separate from the founder-facing prose.
            result['specialist_audit'] = {
                'requested_run_id': state.run_id, 'workspace_id': state.workspace_id,
                'client_id': state.client_id, 'approval_status': state.approval_status,
                'approval_history': state.approval_history,
                'strategy_identity': state.input_payload.get('blueprint_identity'),
                'strategy': {key: state.input_payload.get(key) for key in (
                    'central_thesis', 'growth_opportunity', 'audience', 'key_strategic_choices',
                    'commercial_model', 'assumption_control', 'evidence_and_uncertainty')},
                'source_register': state.input_payload.get('source_register'),
                'evidence_lineage': state.input_payload.get('evidence_lineage'),
                'expected_outputs': result['required_outputs'],
                'specification': FIELDWORK_SPEC, 'specification_sections': ['v7.0', 'v7.1', 'v7.2'],
                'recorded_asset_review_folder_url': state.input_payload.get('asset_review_folder_url'),
                'handback': result['return_to'],
            }
        return result

    def register(self, state, inputs, principal):
        state = self.runtime.runs.load_run(state.run_id)
        if not principal or inputs.get('workspace_id') != state.workspace_id or inputs.get('client_id') != state.client_id:
            raise ValueError('Exact authenticated workspace/client binding required')
        if state.status.value != 'blocked' or not state.current_stage_id:
            raise ValueError('External adoption currently requires a blocked final preparation stage')
        stage = state.stage(state.current_stage_id)
        if stage.side_effect_classification != 'preparation' or state.stages[-1].stage_id != stage.stage_id:
            raise ValueError('External handback cannot bypass later stages or external-action gates')
        producer, version = str(inputs.get('producing_specialist') or '').strip(), str(inputs.get('version') or '').strip()
        title = str(inputs.get('title') or '').strip()
        if not all((producer, version, title)): raise ValueError('Producer, title and version required')
        output = inputs.get('output')
        if output is None and stage.attempts:
            candidate = stage.attempts[-1].get('candidate_artifact') or {}
            location = candidate.get('location')
            if location:
                path = Path(location).resolve()
                path.relative_to(self.runtime.coordinator.artifacts.root.resolve())
                raw = path.read_bytes()
                value = json.loads(raw)
                if _workflow_value_checksum(value) != candidate.get('checksum'):
                    raise ValueError('Existing stage-output bundle checksum mismatch')
                output = {key:value[key] for key in stage.expected_outputs if key in value}
        if not isinstance(output, dict): raise ValueError('Supply the complete externally produced stage-output bundle; no fields will be invented')
        spec = output.get('presentation_specification')
        if isinstance(spec, dict) and any(spec.get(key) not in (None, '', expected)
                for key, expected in (('workspace_id',state.workspace_id),('client_id',state.client_id),('run_id',state.run_id))):
            raise ValueError('Embedded document identity contradicts the engagement')
        if set(output) - set(stage.expected_outputs): raise ValueError('Output bundle cannot replace upstream inputs or governance')
        missing = [key for key in stage.expected_outputs if not output.get(key)]
        if missing: raise ValueError('Stage-output bundle missing required fields: ' + ', '.join(missing))
        files = inputs.get('files')
        if not isinstance(files, list) or not files: raise ValueError('Actual file bytes or verified Drive file required')
        supplied, provenance = {}, []
        for item in files:
            field = str(item.get('output_field') or '')
            if field not in {'review_pdf','editable_pptx'} or field not in stage.expected_outputs or field in supplied: raise ValueError('Invalid/duplicate file-to-stage field')
            name = str(item.get('filename') or '')
            source = 'authenticated_upload'
            if item.get('drive_file_id'):
                drive = self.dispatchers.get('Google Drive')
                if drive is None: raise ValueError('Drive adapter unavailable')
                file_id = str(item['drive_file_id'])
                meta = drive({'execution_mode':'autonomous_read','operation':'get_metadata','target':{'file_id':file_id}})
                if meta.get('verified') is not True: raise ValueError('Drive metadata unverified')
                metadata = meta['metadata']; name = str(metadata['name'])
                if int(metadata.get('size') or MAX_BYTES+1)>MAX_BYTES: raise ValueError('Export native/oversized files to a bounded PDF/PPTX first')
                req = request.Request(drive.api_base+'/files/'+parse.quote(file_id,safe='')+'?alt=media', headers=drive._headers())
                with drive.client.opener(req,timeout=20) as response: data=response.read(MAX_BYTES+1)
                source = metadata.get('webViewLink') or 'drive:file:'+file_id
            else:
                data = base64.b64decode(str(item.get('content_base64') or ''),validate=True)
            if not data or len(data)>MAX_BYTES or Path(name).name != name: raise ValueError('Invalid or oversized document')
            if not ((name.lower().endswith('.pdf') and data.startswith(b'%PDF-')) or
                    (name.lower().endswith('.pptx') and data.startswith(b'PK'))):
                raise ValueError('Only actual PDF/PPTX documents are supported')
            if (field == 'review_pdf' and not name.lower().endswith('.pdf')) or (field == 'editable_pptx' and not name.lower().endswith('.pptx')):
                raise ValueError('Document type does not match its stage role')
            checksum = hashlib.sha256(data).hexdigest()
            directory = self.runtime.coordinator.artifacts.root/'external-files'/checksum
            directory.mkdir(parents=True,exist_ok=True)
            directory.resolve().relative_to(self.runtime.coordinator.artifacts.root.resolve())
            target = directory/name
            if target.is_symlink(): raise ValueError('Document symlinks are not accepted')
            if target.exists() and target.read_bytes()!=data: raise ValueError('Immutable file collision')
            if not target.exists():
                with target.open('xb') as handle: handle.write(data)
            supplied[field] = str(target)
            provenance.append({'field':field,'filename':name,'sha256':checksum,'source':source,'size':len(data)})
        if state.workflow_id == 'growth_blueprint_deliverable_production' and not {'review_pdf','editable_pptx'}.issubset(supplied):
            raise ValueError('Fieldwork contract requires actual review PDF and editable PPTX; candidate cannot substitute placeholders')
        exact = dict(output, **supplied)
        exact['external_document_provenance'] = {'producing_specialist':producer,'version':version,'title':title,
            'submitted_by':principal,'automated_completion':False,'files':provenance,'client_id':state.client_id,'workspace_id':state.workspace_id}
        checksum = _workflow_value_checksum(exact); identity='handback-'+checksum[:24]
        key='document_handback:'+identity
        if key in state.input_payload: return state.input_payload[key]
        artifact=self.runtime.coordinator.artifacts.persist_external_candidate(state,stage.stage_id,exact,identity)
        record={'artifact':artifact_to_dict(artifact),'approval_status':'pending','quality_status':'not_accepted_on_upload',
            'manual_recovery':{'recovery_id':identity,'artifact_title':title,'artifact_version':version,
                'source_uri':provenance[0]['source'],'artifact_checksum':checksum,'output':exact}}
        key='document_handback:'+identity
        if key not in state.input_payload: self.runtime.runs.merge_inputs(state.run_id,{key:record})
        return record

    def draft(self, state, candidate_id):
        state=self.runtime.runs.load_run(state.run_id)
        record=state.input_payload.get('document_handback:'+candidate_id)
        if not isinstance(record,dict): raise ValueError('Exact registered candidate required')
        recovery=record['manual_recovery']
        approval=next((a for a in state.approval_history if a.get('decision')=='manual_recovery_approved'
            and a.get('recovery_id')==candidate_id and a.get('artifact_checksum')==recovery['artifact_checksum']),None)
        if not approval or state.approval_status!='approved': raise ValueError('Exact-document human manual recovery approval required before draft')
        # This bounded adapter prepares internal review only. Real recipients require the existing verified client-delivery boundary.
        provenance=recovery['output']['external_document_provenance']
        pdf=next((f for f in provenance['files'] if f['field']=='review_pdf'),None)
        if pdf is None: raise ValueError('A registered PDF is required for this draft')
        path=Path(recovery['output']['review_pdf']); data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=pdf['sha256']: raise ValueError('Approved file changed')
        subject=f"TEST / INTERNAL REVIEW — {provenance['title']}"
        body=f"Matt,\n\nThe attached {provenance['title']} ({provenance['version']}) was supplied by {provenance['producing_specialist']} and approved through the exact-document manual handback.\n\nPlease review this client-delivery draft before authorising any send. No client contact or publication is authorised. No verified presentation booking link is recorded; agree the meeting invitation separately.\n"
        contract={'execution_mode':'approved_write','approval_granted':True,'operation':'create_draft',
            'idempotency_key':'document-draft:'+recovery['artifact_checksum'],
            'payload':{'recipient_email':'hello@narratiive.com','subject':subject,'body':body,
            'attachments':[{'filename':pdf['filename'],'mime_type':'application/pdf','content_base64':base64.b64encode(data).decode()}]}}
        gmail=self.dispatchers.get('Gmail')
        if gmail is None: raise ValueError('Gmail adapter unavailable')
        receipt=gmail(contract)
        if receipt.get('verified') is not True or receipt.get('sent') is not False or not receipt.get('draft_id'):
            raise ValueError('Unsent Gmail draft not verified')
        self.runtime.runs.record_external_action(state.run_id,idempotency_key=contract['idempotency_key'],
            receipt=dict(receipt,kind='external_document_internal_draft',candidate_id=candidate_id,attachment_sha256=pdf['sha256'],
                         recipient='hello@narratiive.com',subject=subject,body=body,send_authorised=False))
        return dict(receipt,subject=subject,body=body,attachment_sha256=pdf['sha256'],send_authorised=False)


def format_document_brief(state, brief):
    """Bounded human brief for the published n8n legacy-Markdown send node.

    Escape before measuring: the existing formatter caps responses at 3500.
    Do not flatten arbitrary strategy JSON or imply missing evidence is verified.
    """
    def escape(value):
        text = " ".join(str(value).split())
        return "".join("\\" + char if char in "\\_*`[" else char for char in text)

    lines = []
    def add(label, value, limit=400):
        if not value:
            return
        text = " ".join(str(value).split())
        if len(text) > limit:
            text = text[:limit-1] + "…"
        # Count escaped characters, not just source characters, and never split
        # an escape pair. Long dynamic values cannot crowd out required guidance.
        cap = min(limit, 300) if label != "Exact engagement" else 400
        if text.startswith("https://"):
            cap = len(escape(text))  # Include a complete URL or omit its line; never invent a truncated link.
        escaped = []
        for char in text:
            token = escape(char) if not char.isspace() else " "
            if sum(len(item) for item in escaped) + len(token) > cap:
                escaped.append("…")
                break
            escaped.append(token)
        line = escape(label + ": ") + " " + "".join(escaped)
        lines.append((label, line))

    if state.workflow_id == 'growth_blueprint_deliverable_production':
        return format_fieldwork_specialist_brief(state, brief)

    stage = state.stage(state.current_stage_id) if state.current_stage_id else None
    diagnostic = state.input_payload.get("diagnostic_input_package") or {}
    diagnostic = diagnostic.get("diagnostic", diagnostic) if isinstance(diagnostic, dict) else {}
    raw = diagnostic.get("raw_answers") or {}
    add("Commissioning brief", brief.get("client_name") or brief.get("client"), 180)
    add("Exact engagement", state.run_id, 400)
    add("Recorded stage", f"{state.workflow_id} / {state.current_stage_id or 'none'} — {state.status.value}; approval: {state.approval_status}", 350)
    add("Scope", "This exact run only; later child engagements are separate. This read-only brief does not reopen or approve work.")
    strategy = brief.get("strategy_from_engagement")
    if isinstance(strategy, dict):
        opportunity = next((strategy.get(key) for key in ("growth_opportunity", "strategic_opportunity", "thesis_statement") if isinstance(strategy.get(key), str)), None)
    else:
        opportunity = strategy if isinstance(strategy, str) else None
    add("Opportunity" if opportunity else "Recorded hypothesis, not approved strategy", opportunity or raw.get("hypothesis") or diagnostic.get("challenge") or "No strategic opportunity is recorded; Matt must supply or identify the approved strategy.", 420)
    focus = diagnostic.get("recommended_actions")
    add("Recommended Fieldwork focus", "; ".join(str(item) for item in focus[:3]) if isinstance(focus, list) else "Validate the growth audience, commercial evidence and strategic choices against the approved strategy.", 320)
    missing = raw.get("unknowns")
    add("Matt / missing evidence", "; ".join(str(item) for item in missing[:5]) if isinstance(missing, list) else "Confirm current strategy, scope and evidence gaps before commissioning.", 380)
    add("Deadline", brief.get("deadline"), 100)
    add("Fieldwork v7 specification", FIELDWORK_SPEC, 200)
    urls = raw.get("source_urls") or []
    register = brief.get("source_register") or {}
    if isinstance(register, dict):
        urls = list(urls) + [entry.get("location") for entry in register.get("entries", []) if isinstance(entry, dict)]
    for url in list(dict.fromkeys(str(url) for url in urls if url))[:3]:
        if url.startswith("https://") and len(url) <= 180:
            add("Recorded evidence reference", url, 180)
    if not urls:
        add("Evidence", "No source URLs recorded on this exact run; supply evidence before production.")
    add("Production workspace", "No verified production-folder link is exposed by this brief; do not assume a destination.")
    eligible = bool(stage and state.status.value == "blocked" and stage.side_effect_classification == "preparation" and state.stages[-1].stage_id == stage.stage_id and {"review_pdf", "editable_pptx"}.issubset(stage.expected_outputs))
    add("Next action", "Return PDF/PPTX and the complete declared stage-output bundle with producer/version; register a candidate for Matt's exact-version review. Upload is not approval." if eligible else "This run cannot adopt an external document at its current boundary. Identify the intended eligible preparation run before handback; no upstream work will be replayed.", 350)
    add("Safety", "No file created, production invoked, approval changed or client contact authorised.")
    required = {"Fieldwork v7 specification", "Production workspace", "Next action", "Safety"}
    remaining = 3400 - sum(len(line)+1 for label, line in lines if label in required)
    selected = []
    for label, line in lines:
        if label in required:
            selected.append(line)
        elif len(line)+1 <= remaining:
            selected.append(line)
            remaining -= len(line)+1
    return "\n".join(selected)


def format_fieldwork_specialist_brief(state, brief):
    """A complete copyable commission from this exact Fieldwork record only."""
    payload = state.input_payload
    problem = payload.get('growth_opportunity') or {}
    thesis = payload.get('central_thesis') or {}
    missing = []
    if state.approval_status != 'approved': missing.append('approved Fieldwork evidence')
    if not isinstance(problem, dict) or not problem.get('diagnosis'): missing.append('central strategic problem')
    if not isinstance(thesis, dict) or not thesis.get('insight'): missing.append('strategic recommendation')
    register = payload.get('source_register') or {}
    entries = register.get('entries', []) if isinstance(register, dict) else []
    if not entries: missing.append('source register')
    model = payload.get('commercial_model') or {}
    uncertainty = payload.get('evidence_and_uncertainty') or []
    if not uncertainty: missing.append('evidence limitations and known assumptions')
    if missing:
        return 'Fieldwork commissioning brief unavailable: missing ' + ', '.join(missing) + '. Matt: select the exact approved Fieldwork engagement or supply these records. No run was substituted or changed.'
    synthetic = any(item.get('approval_kind') == 'synthetic_rehearsal' for item in state.approval_history)
    approval = 'Fictional rehearsal approval only; not Matt/client approval.' if synthetic else 'Recorded Fieldwork approval; no new work or release authorised.'
    sources = []
    for entry in entries:
        location = str(entry.get('location') or '')
        if location.startswith('https://'):
            sources.append(str(entry.get('source_id') or '') + ' ' + location)
    model_note = 'No verified client baseline: do not invent a forecast, profit or ROI.'
    if model.get('classification') == 'illustrative_scenario_model':
        scenarios = model.get('scenarios') or []
        parts = []
        for scenario in scenarios:
            if all(scenario.get(key) is not None for key in ('additional_accounts', 'annual_account_revenue', 'year_one_ramp', 'incremental_annual_revenue')):
                parts.append(f"{scenario['additional_accounts']} accounts × £{scenario['annual_account_revenue']:g} × {scenario['year_one_ramp']:g} = £{scenario['incremental_annual_revenue']:g}")
        if parts:
            basis = '/'.join(str(entry.get('source_id')) for entry in entries if entry.get('classification') == 'assumption') or 'Recorded model'
            model_note = basis + ' illustrative assumptions, year-one revenue, not forecast/profit: ' + '; '.join(parts) + '.'
    limits = ' '.join(str(item) for item in uncertainty)
    gaps = (payload.get('assumption_control') or {}).get('missing_evidence', [])
    if 'failed' in limits.lower() and 'verif' in limits.lower():
        verification_note = 'Public-page re-verification failed in the supplied pack; source links are documentary leads, not independently verified facts.'
    else:
        verification_note = 'Preserve the source register’s verification status; do not treat supplied links as independently verified facts.'
    handback_note = 'The completed run cannot adopt a new version without an eligible preparation boundary.' if state.status.value == 'complete' else 'Ask Tony to verify the current stage is an eligible blocked final-preparation boundary before adoption.'
    paragraphs = [
        f"{brief.get('client_name') or brief.get('client')} — Fieldwork presentation. {approval}",
        'Problem: ' + str(problem['diagnosis']),
        "Tony recommends: revise the Fieldwork deck from the recorded approved evidence below; preserve its strategic focus.",
        'Copy to Claude:',
        'Prepare the complete Fieldwork deck for ' + str(brief.get('client_name') or brief.get('client')) + ' under Matt’s direction. Strategic direction: ' + str(thesis['insight']),
        'Evidence limits: ' + str(uncertainty[0]),
        model_note,
        'Sources (recorded, not newly verified): ' + '; '.join(sources),
        verification_note,
        'Known gaps: ' + '; '.join(str(item) for item in gaps),
        'Follow Fieldwork v7, including v7.1 evidence rules and v7.2 handback: ' + FIELDWORK_SPEC,
        'Use Rave’s six-act argument, competitor/audience evidence, five-lever table, clear SO WHAT and 90-day marketing activation. No copied findings or invented certainty.',
        'Return editable PPTX + matching PDF, presentation specification, commercial model, source register, visual QA, production evidence and release recommendation. Cite claims on slides; retain facts/inferences/assumptions and QA gaps.',
        'Handback: follow v7.2 filenames/versioning; return producer, version, source/strategy references and file manifest to Matt. Registration and exact-version approval remain separate. ' + handback_note,
        'Matt next: confirm scope, deadline and a verified Fieldwork working folder (not a stills folder); copy this brief to Claude. Return files for exact-version review. No automatic production, send or publication.',
    ]
    # Keep the already deployed Telegram transport/escaping contract unchanged.
    text = '\n\n'.join(paragraphs)
    escaped = ''.join('\\' + char if char in '\\_*`[' else char for char in text)
    if len(escaped) > 3400:
        return 'The exact Fieldwork evidence exceeds one complete Telegram commissioning brief. Matt: request an authorised linked brief before commissioning; no evidence was truncated, file created or run substituted.'
    return escaped
