"""External document candidates using existing immutable storage/manual recovery.

No approval, stage completion, client send or publication occurs on registration.
"""
import base64
import hashlib
import json
from pathlib import Path
from urllib import request, parse
from runtime.serialization import artifact_to_dict
from runtime.tony_workflow_runtime import _workflow_value_checksum

RAVE_REFERENCE = 'https://drive.google.com/file/d/1ciJ2-Y8O0MIS5DAIe_tuoS3OXbIKUx--/view'
FIELDWORK_SPEC = 'https://docs.google.com/document/d/1KmY6uMSbdhGbl730bdXOPJh53nfhYjve6AVzexkXM1I/edit'
MAX_BYTES = 5_000_000


class DocumentHandbackService:
    def __init__(self, runtime, dispatchers):
        self.runtime = runtime
        self.dispatchers = dispatchers or {}

    def brief(self, state):
        return {'client': state.client_id, 'engagement': state.run_id, 'workflow': state.workflow_id,
            'required_outputs': list(state.stage(state.current_stage_id).expected_outputs) if state.current_stage_id else [],
            'strategy_identity': state.input_payload.get('blueprint_identity'),
            'evidence': state.input_payload.get('evidence_lineage', []),
            'reference': FIELDWORK_SPEC if state.workflow_id == 'growth_blueprint_deliverable_production' else None,
            'methodology_reference': RAVE_REFERENCE if state.workflow_id == 'growth_blueprint_deliverable_production' else None,
            'constraints': state.input_payload.get('production_constraints', []),
            'deadline': 'Not supplied; agree with Matt.', 'quality': 'Use the stage contract and source evidence; upload is not quality acceptance.',
            'return_to': 'Register against this exact engagement with producer, version, PDF and complete stage-output bundle. Then Matt reviews the exact candidate before manual recovery.',
            'automation': 'No specialist generation invoked.'}

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
