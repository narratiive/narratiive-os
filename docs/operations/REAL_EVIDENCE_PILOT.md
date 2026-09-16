# Real-evidence pilot runbook

This runbook controls the first authorised real-company evidence pilot through:

```text
Diagnostic → Blueprint Lite → Discovery Preparation → Growth Sprint Proposal
→ Research Engine → Growth Blueprint
```

It does not authorise client communication, meeting booking, publication,
delivery, Drive sharing, commercial commitment or any other external write.
Use a unique `.invalid` contact identity even though the underlying company
evidence is real and authorised.

## 1. Prepare the private manifest

Create the manifest outside Git and keep it in the pilot's access-controlled
workspace. It must use schema version 1 and contain:

- an `AUTHORISED REAL-EVIDENCE PILOT ...` label;
- safe `pilot_id`, `workspace_id` and `client_id` identifiers;
- a unique `.invalid` synthetic contact email;
- explicit authorisation (`status`, `approved_by`, `approved_at`, and purpose);
- the exact workflow and approval-gate lists below;
- `external_actions_allowed: false`;
- one or more evidence-source descriptors with explicit approved policy and
  origin, capture time, and permitted-use provenance.

The manifest contains descriptors, never credentials or copied evidence
content. Credential-like field names are rejected. The exact canonical lists
are:

```json
{
  "workflow_ids": [
    "growth_diagnostic_to_blueprint_lite",
    "blueprint_lite_to_discovery_preparation",
    "discovery_evidence_to_growth_sprint_proposal",
    "growth_sprint_to_research_engine",
    "research_to_growth_blueprint"
  ],
  "approval_gates": [
    "growth_diagnostic_to_blueprint_lite",
    "blueprint_lite_to_discovery_preparation",
    "discovery_evidence_to_growth_sprint_proposal",
    "research_to_growth_blueprint"
  ]
}
```

## 2. Preflight and adapter checks

Load runtime configuration without printing it. Then run:

```bash
.venv/bin/python scripts/real_evidence_pilot.py preflight --manifest /private/path/pilot.json
.venv/bin/python scripts/validate_business_adapters.py
```

Preflight writes a scoped append-only receipt containing only identifiers,
manifest checksum, source IDs, required gates and the prohibition on external
actions. Repeating an unchanged preflight is suppressed. A missing adapter must
remain an explicit blocker if that pilot step depends on it; do not substitute a
browser session or manually copied unprovenanced data.

## 3. Run the controlled journey

1. Submit the authorised diagnostic using the synthetic `.invalid` identity.
   Confirm the resulting lead and workflow IDs before continuing.
2. Wait for Blueprint Lite quality validation. Review the persisted artefact,
   then explicitly approve or request revision through Tony.
3. Continue to Discovery Preparation. Review evidence/hypothesis separation,
   gaps, questions and meeting objective, then explicitly approve or revise.
4. Ingest discovery notes/transcript with exact source provenance. If Fireflies
   is used, retain its transcript ID or exact Calendar event ID. Do not infer
   answers that are absent from the evidence.
   An approved Research Engine source uses the canonical descriptor below; the
   transcript identifier remains provider provenance and no meeting mutation is
   authorised:

   ```json
   {
     "source_id": "pilot-approved-discovery-meeting",
     "source_type": "fireflies_transcript",
     "uri": "fireflies:transcript:<exact-transcript-id>",
     "policy": {"approved": true}
   }
   ```
5. Continue to Growth Sprint Proposal. Review scope and commercial inputs, then
   explicitly approve the internal scope. Do not send the draft communication.
6. Continue with only approved research sources. Inspect Research Engine
   provenance, contradictions and gaps. Use Tony's `additional_research`
   operation for a specific gap/question/hypothesis when necessary; do not use
   an internal runtime invocation.
   If an OpenClaw Research specialist has already completed the substantive
   work, promote that final completed session result with
   `scripts/import_openclaw_research_evidence.py` instead of running it again.
   The import requires an explicit approver and rationale, accepts only the
   canonical Research session store, and creates an immutable, checksum-backed
   source descriptor inside the scoped Research Engine workspace. Treat the
   imported report as specialist synthesis: material claims still require
   verification against its cited primary sources.
7. Continue to Growth Blueprint. Confirm the substantive quality contract and
   lineage passed. Leave the result at human review unless a separate,
   authorised internal approval is deliberately recorded.

At every checkpoint use Tony's status, approvals, blockers and latest-artefact
operations. Runtime state is execution truth; Notion is a separately approved
business projection.

Project the live acceptance programme without creating a second state store:

```bash
.venv/bin/python scripts/acceptance_programme_status.py \
  --scenario-client-id <persisted-client-id> \
  --format text
```

Use `--format json` for machine-readable status. The projection reports the
deployed revision, service health, current scenario, last quality-verified
checkpoint, failures, required human decisions, architectural conflicts and
capability evidence. It derives those claims from workflow snapshots,
artefacts, receipts, conversation-work records and the deployment receipt; it
does not mutate or supersede any of them.

To prove executive attention suppression against the deployed bridge, first
confirm that the current day's scheduled morning brief has already completed.
Then run the acceptance probe through the protected runtime environment:

```bash
.venv/bin/python scripts/run_with_env.py ~/.config/narratiive/runtime.env \
  .venv/bin/python scripts/accept_attention_suppression.py --apply
```

The probe fails closed unless today's delivery key already exists, so it cannot
initiate a new brief. It verifies that persisted suppressed/archived/test or
completed leads remain absent from both the live morning projection and direct
lead view, then proves a repeated scheduled delivery is stopped before
transport. Its revision-bound receipt is consumed by the existing acceptance
programme projection.

## 4. Acceptance check

```bash
.venv/bin/python scripts/real_evidence_pilot.py status --manifest /private/path/pilot.json
```

Acceptance requires all five durable workflow runs, artefacts and quality
results; recorded or currently pending human gates; a complete Research Engine
run; and `external_action_taken: false` throughout. The status output contains
IDs and gate state, not evidence content.

Stop immediately if workspace/client identity is inconsistent, provenance is
missing, an approval is ambiguous, a quality gate fails, an adapter is
unavailable, or any external action is reported. Preserve the state and attempt
evidence for diagnosis; do not weaken a gate or overwrite an artefact.
