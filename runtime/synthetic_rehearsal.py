"""Bounded, explicitly synthetic progression through the existing workflow runtime.

No payments, client contact, publication or final asset approval are available.
All work remains in canonical WorkflowState and append-only workflow events.
"""
from __future__ import annotations
import hashlib
import json
from collections.abc import Mapping
from typing import Any
from runtime.models import WorkflowStatus
from runtime.repositories import WorkflowEvent
from runtime.workflow_entity_classification import INTERNAL_SYNTHETIC_TEST

ACTOR = 'Synthetic rehearsal reviewer (not human or client approval)'
PROPOSAL = 'discovery_evidence_to_growth_sprint_proposal'
ASSETS = 'creative_bible_to_asset_production'
ALLOWED = frozenset({'strategic_synthesis_to_strategy_thesis','strategy_thesis_to_growth_blueprint',
    'growth_blueprint_deliverable_production','growth_blueprint_to_campaign_world',
    'campaign_world_to_creative_bible',ASSETS})


def checksum(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()


class SyntheticRehearsalService:
    def __init__(self, runtime, classifications, states_loader):
        self.runtime=runtime
        self.classifications=classifications
        self.states_loader=states_loader

    def _canonical(self,state):
        canonical=self.runtime.runs.load_run(state.run_id)
        if (state.workspace_id,state.client_id,state.entity_id)!=(canonical.workspace_id,canonical.client_id,canonical.entity_id):
            raise PermissionError('Synthetic rehearsal scope mismatch')
        classified=self.classifications.latest(canonical.workspace_id).get(canonical.entity_id)
        if not classified or classified.classification!=INTERNAL_SYNTHETIC_TEST:
            raise PermissionError('Authenticated synthetic classification required')
        return canonical

    def _event(self,state,kind,payload):
        identity='synthetic-'+checksum([state.workspace_id,state.run_id,kind,payload])[:32]
        log=self.runtime.runs.event_log
        with log.transaction(state.run_id):
            for event in log.read(state.run_id):
                if event.event_id==identity:return event
                if kind in {'synthetic_proposal_accepted','synthetic_payment_recorded','synthetic_rehearsal_authorised'} and event.event_type==kind:
                    raise ValueError('Conflicting synthetic commercial evidence is already recorded')
            event=WorkflowEvent.create(event_id=identity,run_id=state.run_id,event_type=kind,
                payload=payload,workspace_id=state.workspace_id)
            log.append(event)
            return event

    def enrol(self,state,*,authorisation_reference,scope_instruction):
        state=self._canonical(state)
        if state.workflow_id!=PROPOSAL or state.approval_status!='approved':
            raise ValueError('Exact approved proposal required')
        artifact=state.stages[-1].output_artifacts[-1]
        approval=next((a for a in reversed(state.approval_history)
            if a.get('approval_binding',{}).get('artifact_checksum')==artifact.checksum),None)
        decision=approval.get('approval_binding',{}).get('human_decision',{}) if approval else {}
        if not (decision.get('verbatim_current_human_instruction_verified') is True
                and decision.get('explicit_decision_intent')=='approve'
                and decision.get('scope')=='fictional_rehearsal_only'):
            raise PermissionError('Exact human approval for fictional rehearsal required')
        if not authorisation_reference.strip() or not scope_instruction.strip():
            raise ValueError('Current user rehearsal instruction and source reference required')
        payload=dict(classification='SYNTHETIC / TEST',provider='none',financial_authorisation=False,
            proposal_artifact_id=artifact.artifact_id,proposal_checksum=artifact.checksum,
            proposal_version=artifact.metadata.get('version'),actual_human_approver=approval['approver'],
            authorisation_reference=authorisation_reference,scope_instruction=scope_instruction,
            maximum_assets=2,allowed_capabilities=['image_generation'],stop_at='asset_review',
            real_client_contact=False,real_payment=False,publication=False,final_asset_approval=False)
        accepted=self._event(state,'synthetic_proposal_accepted',payload)
        self._event(state,'synthetic_payment_recorded',{**payload,'payment_status':'simulated_paid','stripe_transaction':None})
        policy=self._event(state,'synthetic_rehearsal_authorised',{**payload,'acceptance_event_id':accepted.event_id})
        return {'proposal_run_id':state.run_id,'policy_event_id':policy.event_id,
            'maximum_assets':2,'allowed_capabilities':['image_generation'],'stop_at':'asset_review'}

    def policy(self,state):
        state=self._canonical(state)
        reference=state.input_payload.get('_synthetic_rehearsal')
        if not isinstance(reference,Mapping):raise PermissionError('Rehearsal policy binding missing')
        proposal=self.runtime.runs.load_run(str(reference.get('proposal_run_id') or ''))
        if (proposal.workspace_id,proposal.client_id,proposal.entity_id)!=(state.workspace_id,state.client_id,state.entity_id):
            raise PermissionError('Rehearsal proposal lineage is outside current client')
        cursor=state
        visited=set()
        while cursor.run_id!=proposal.run_id:
            if cursor.run_id in visited or len(visited)>20:
                raise PermissionError('Invalid rehearsal lineage')
            visited.add(cursor.run_id)
            parent=cursor.input_payload.get('_lineage',{}).get('parent_run_id')
            if not parent:raise PermissionError('Rehearsal run is not descended from its approved proposal')
            cursor=self.runtime.runs.load_run(str(parent))
            if (cursor.workspace_id,cursor.client_id,cursor.entity_id)!=(state.workspace_id,state.client_id,state.entity_id):
                raise PermissionError('Rehearsal lineage crossed a client boundary')
        event=next((e for e in self.runtime.runs.event_log.read(proposal.run_id)
            if e.event_type=='synthetic_rehearsal_authorised' and e.event_id==reference.get('policy_event_id')),None)
        if not event or event.payload.get('stop_at')!='asset_review' or event.payload.get('maximum_assets')!=2:
            raise PermissionError('Canonical rehearsal authorisation not found')
        return event

    def review(self,state):
        state=self._canonical(state);policy=self.policy(state)
        if state.status is not WorkflowStatus.AWAITING_APPROVAL or state.workflow_id not in ALLOWED:
            raise PermissionError('This gate is outside the bounded rehearsal')
        if state.workflow_id==ASSETS and state.input_payload.get('asset_versions'):
            raise PermissionError('Final generated-asset approval belongs to Matt')
        if state.workflow_id==ASSETS:
            tasks=state.input_payload.get('production_tasks')
            if not isinstance(tasks,list) or len(tasks)!=2 or any(t.get('required_capability')!='image_generation' for t in tasks):
                raise PermissionError('Rehearsal permits exactly two image production jobs')
        artifact=next(a for stage in reversed(state.stages) for a in reversed(stage.output_artifacts))
        binding={'synthetic_rehearsal':True,'human_approval':False,'policy_event_id':policy.event_id,
            'artifact_id':artifact.artifact_id,'artifact_checksum':artifact.checksum,
            'real_client_contact':False,'publication_authorised':False}
        self._event(state,'synthetic_internal_gate_accepted',binding)
        self.runtime.coordinator.approve(state.run_id,approver=ACTOR,
            rationale='Explicitly simulated internal review under the bounded user-authorised fictional rehearsal.',
            approval_binding=binding)
        state=self.runtime.runs.load_run(state.run_id)
        if state.workflow_id=='growth_blueprint_to_campaign_world':
            brief=self.runtime.campaign_world_selection_brief(state.run_id)
            candidates=[c for c in brief['candidates'] if c['ready_for_matt']]
            if not candidates:raise ValueError('No quality-forwarded Campaign World candidate')
            selected=candidates[0]
            self.runtime.select_campaign_world(state.run_id,candidate_id=selected['candidate_id'],
                candidate_checksum=selected['candidate_checksum'],approver=ACTOR,
                rationale='Synthetic creative-direction selection; not a Matt approval.',synthetic_rehearsal=True)
        if state.workflow_id=='campaign_world_to_creative_bible':
            brief=self.runtime.creative_bible_approval_brief(state.run_id)
            self.runtime.approve_creative_bible(state.run_id,creative_bible_checksum=brief['creative_bible_checksum'],
                approver=ACTOR,rationale='Synthetic creative-direction review; not a Matt approval.',synthetic_rehearsal=True)
        return self.runtime.runs.load_run(state.run_id)
