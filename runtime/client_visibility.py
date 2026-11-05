"""Read-only client views over recorded workflow identities and handoff lineage."""
from collections.abc import Mapping
import re
from urllib.parse import quote
from runtime.workflow_portfolio import project_client_portfolio
from runtime.workflow_mission_control import workflow_state_name


PRODUCTS = {
    'growth_diagnostic_to_blueprint_lite': ('Groundwork', 'prospect research'),
    'blueprint_lite_to_discovery_preparation': ('Groundwork', 'Discovery preparation'),
    'discovery_evidence_to_growth_sprint_proposal': ('Fieldwork', 'proposal review'),
    'growth_sprint_to_research_engine': ('Fieldwork', 'research'),
    'research_to_strategic_synthesis': ('Fieldwork', 'strategic synthesis'),
    'strategic_synthesis_to_strategy_thesis': ('Fieldwork', 'strategy thesis'),
    'strategy_thesis_to_growth_blueprint': ('Fieldwork', 'strategy development'),
    'research_to_growth_blueprint': ('Fieldwork', 'strategy development'),
    'growth_blueprint_deliverable_production': ('Fieldwork', 'strategy review'),
    'growth_blueprint_to_campaign_world': ('Sketchbook', 'creative world'),
    'campaign_world_to_creative_bible': ('Sketchbook', 'creative direction'),
    'creative_bible_to_asset_production': ('Launchpad', 'asset production'),
    'asset_review_to_delivery_preparation': ('Launchpad', 'delivery preparation'),
    'delivery_to_follow_up_next_action': ('Launchpad', 'performance follow-up'),
}


def aliases(state):
    values = [state.client_id, state.entity_id, workflow_state_name(state)]
    for context in [state.input_payload, *(state.input_payload.get(key) for key in
                    ('client_context', 'company_context', 'commercial_context'))]:
        if isinstance(context, Mapping):
            values.extend(context.get(key) for key in ('name', 'company', 'company_name', 'brand_name'))
            recorded = context.get('aliases', [])
            if isinstance(recorded, list): values.extend(v for v in recorded if isinstance(v, str))
    return {str(v).strip().casefold() for v in values if isinstance(v, str) and v.strip()}


def client_engagements(states, reference=''):
    """Use explicit same-workspace parent edges; never merge separate engagements by name."""
    states = tuple(s for s in states if s.workflow_id in PRODUCTS)
    nodes = {(s.workspace_id, s.run_id): s for s in states}
    parents = {key: key for key in nodes}
    def root(key):
        seen = set()
        while parents[key] != key and key not in seen:
            seen.add(key); key = parents[key]
        return key
    for key, state in nodes.items():
        lineage = state.input_payload.get('_lineage')
        parent = (state.workspace_id, lineage.get('parent_run_id')) if isinstance(lineage, Mapping) else None
        if parent in nodes and root(key) != root(parent): parents[root(key)] = root(parent)
    query = reference.strip().casefold()
    matching = {key for key, s in nodes.items() if query in aliases(s)} if query else set(nodes)
    if query and not matching:
        # Recognised name prefix at a word boundary, not a fuzzy/internal-ID substring.
        matching = {key for key,s in nodes.items() if any(
            re.match(re.escape(query) + r'\b', value) for value in aliases(s))}
    selected_roots = {root(key) for key in matching}
    groups = {}
    for key,state in nodes.items():
        if root(key) in selected_roots: groups.setdefault(root(key), []).append(state)
    result = []
    def campaign_for(state):
        seen = set()
        while state is not None and (state.workspace_id, state.run_id) not in seen:
            seen.add((state.workspace_id, state.run_id))
            identity = state.input_payload.get('campaign_identity')
            if isinstance(identity, Mapping) and identity.get('campaign_id'):
                return str(identity['campaign_id'])
            lineage = state.input_payload.get('_lineage')
            state = nodes.get((state.workspace_id, lineage.get('parent_run_id'))) if isinstance(lineage, Mapping) else None
        return None
    partitions = []
    for group in groups.values():
        campaign_ids = {campaign_for(s) for s in group} - {None}
        if len(campaign_ids)>1:
            for campaign_id in sorted(campaign_ids):
                partitions.append([s for s in group if campaign_for(s) in {None, campaign_id}])
        else: partitions.append(group)
    for group in partitions:
        rows = project_client_portfolio(group)
        row = max(rows, key=lambda r:(r['current_gate'],r['updated_at'],r['current_run_id']))
        current = next(s for s in group if s.run_id == row['current_run_id'])
        row = dict(row, campaign_id=campaign_for(current) or row["campaign_id"])
        product, phase = PRODUCTS[current.workflow_id]
        result.append((current, dict(row, commercial_product=product, phase=phase,
            engagement_started_at=min(s.created_at for s in group))))
    return tuple(sorted(result, key=lambda pair:(pair[1]['company'].casefold(), pair[1]['engagement_started_at'],pair[0].run_id)))


def verified_review_link(state, backend):
    """Reuse the existing checksum-validated review manifest and exact delivery receipt."""
    try: detail = backend.artifact_detail(state)
    except (ValueError, OSError, LookupError): return None
    if not detail.get('human_review_artifact'): return None
    artifact = detail.get('approved_artifact') or {}
    for entry in reversed(state.external_action_receipts):
        receipt = entry.get('receipt') or {}
        if (receipt.get('kind') == 'internal_artifact_review_delivery'
            and receipt.get('artifact_id') == artifact.get('artifact_id')
            and receipt.get('artifact_checksum') == artifact.get('artifact_checksum')
            and receipt.get('review_artifact_checksum') == detail['human_review_artifact'].get('checksum')
            and receipt.get('recipient') == 'hello@narratiive.com'
            and receipt.get('message_id')):
            return 'https://mail.google.com/mail/u/0/#all/' + quote(str(receipt.get('thread_id') or receipt['message_id']),safe='')
    return None


def client_summary(state, row, review_link):
    status = state.status.value
    if status in {'blocked','failed'}:
        code = str(state.blocker or '')
        if 'quality_failed' in code:
            issue = 'Quality review requires specialist correction.'
        elif 'retry_policy_exhausted' in code or 'timeout' in code:
            issue = 'Provider execution failed after its permitted attempts; technical recovery is required.'
        elif 'inputs' in code:
            issue = 'Required handoff inputs are missing or invalid.'
        else: issue = 'A recorded operational blocker needs investigation.'
        action = 'Matt: no approval requested while this is blocked.'
    elif state.approval_status == 'pending':
        issue = 'Awaiting your review.'
        action = 'Matt: review this exact version, then approve or request changes.'
    elif status == 'complete':
        issue = 'Current step completed; no later completion is claimed.'
        action = 'Matt: no new approval requested.'
    else:
        issue = 'Work is in progress.'
        action = 'Matt: no action required at this stage.'
    link = 'Review: ' + review_link if review_link else 'No verified current review link is recorded.'
    name = row['company']
    if '_' in name or re.search(r'-\d{6,}', name): name = 'Client name not supplied'
    recorded = row['engagement_started_at'][:16].replace('T',' ')
    return (f"{name} (recorded {recorded}) — {row['commercial_product']} / {row['phase']}: {status.replace('_',' ')}. "
            f"{issue} {action} {link}")
