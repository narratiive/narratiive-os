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
5. Continue to Growth Sprint Proposal. Review scope and commercial inputs, then
   explicitly approve the internal scope. Do not send the draft communication.
6. Continue with only approved research sources. Inspect Research Engine
   provenance, contradictions and gaps. Use Tony's `additional_research`
   operation for a specific gap/question/hypothesis when necessary; do not use
   an internal runtime invocation.
7. Continue to Growth Blueprint. Confirm the substantive quality contract and
   lineage passed. Leave the result at human review unless a separate,
   authorised internal approval is deliberately recorded.

At every checkpoint use Tony's status, approvals, blockers and latest-artefact
operations. Runtime state is execution truth; Notion is a separately approved
business projection.

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
