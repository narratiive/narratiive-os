# Issue #477 — auditable customer journey trace

Date: 16 October 2026

Synthetic customer: **FIELDWORK (explicitly fictional)**

Safety mode: read-only live probes plus isolated local production; no outreach, external writes, publication, media spend, deployment or production configuration change.

## Executive outcome

**NO-GO for a paying customer journey.**

The system has real working foundations: Tony and its specialist fleet are live, Gmail/Notion/Drive/Calendar/Fireflies/Telegram authenticate, the unified inbound n8n workflow is active, and FIELDWORK can produce a rendered seven-chapter Blueprint with QA and a blocking approval checkpoint. It does not yet prove the connected lifecycle. No controlled email arrived, no synthetic Notion lead was written, no Telegram lifecycle notification was sent, no Fireflies transcript existed, no follow-up or proposal traversed Gmail, and no acceptance/payment event entered the workflow.

## Trace

| # | Trigger → processing → evidence → next step | Classification | Observable evidence | Latency / retry |
|---:|---|---|---|---|
| 1 | Synthetic inquiry arrives in Gmail | **NOT TESTED** | Gmail profile and a bounded search both returned `VERIFIED LIVE`; fictional marker result count was 0. No external test mailbox message was sent. | Safe search completed inside Tony's 11.314 s two-surface run. |
| 2 | Gmail watcher detects and routes inquiry | **NOT WORKING** | LaunchAgent is loaded at a 900-second interval but reported `runs=0`, `state=not running`, and no exit. Its last output log was from 17 September 2026. It was not manually triggered because it can write Notion and send Telegram. | No current execution evidence. |
| 3 | n8n deduplicates and creates canonical Notion lead | **NOT TESTED** | n8n health passed. Active workflow `l6TysPR86l5VAoXc`, “Narratiive - Unified Inbound Lead Intake + Tony Sync”, version 56, contains find-existing, duplicate decision, Notion create and Tony sync nodes. No webhook POST was made, so no write or replay was observed. | Metadata read only. |
| 4 | Notion persists lead and status | **NOT TESTED** | Notion data source `34b0c9cf-a8f2-80af-98e4-000b95243de6` authenticated and returned a verified zero-mutation search. No synthetic page was created. | Included in Tony's 11.314 s two-surface run. |
| 5 | Telegram alerts Matt | **NOT TESTED** | Bot identity and webhook both verified live; webhook configured, zero pending updates and no last error. No message was sent because that is an external write requiring scoped approval. | Read-only API probes only. |
| 6 | Tony reads state, uses tools and delegates | **VERIFIED LIVE** | Effective tool run `e5018f26-d150-4b0b-99cb-5adc9c2757a4`; safe-read runs `c8d039ac-c55b-43e3-be78-224955d5b1c9` and `0c98ea9c-014e-43ca-be6d-f350b8eace94`; authenticated Research delegation completed via push. | 25.177 s tool inventory; 47.261 s six-surface orchestration; 11.314 s corrected Gmail/Notion retry. |
| 7 | Tony sustains the customer handoff conversation | **NOT WORKING** | Full authenticated acceptance reached every scenario, but `contextual_action` returned “No response from OpenClaw.” The old predicate incorrectly counted it as passed. The predicate is repaired in this branch; runtime behaviour still needs correction. | Full sequence took about 157 s. |
| 8 | Blueprint Lite / founder discovery brief | **NOT TESTED** | No inquiry was ingested and no governed Blueprint Lite run was commissioned for this trace. | Blocked by stages 1–5. |
| 9 | Consented discovery call → Fireflies transcript | **NOT TESTED** | Fireflies authentication, transcript-discovery permission and transcript fields verified live. Bounded transcript list contained zero records, so ingestion, summary, actions and 10–20 minute follow-up latency were not testable. | Connector probe passed; lifecycle latency unavailable. |
| 10 | Tailored Gmail follow-up and Telegram approval | **NOT TESTED** | Gmail and Telegram are live for reads; no draft, approval request or send was created. | Approval boundary respected. |
| 11 | Proposal sent, external recipient accepts, thread/status advance | **NOT TESTED** | No controlled external recipient was supplied. No send or acceptance was simulated as if live. | No event. |
| 12 | Contract and deposit | **NOT WORKING** | Repository search found commercial-close attestations but no sandbox contract/payment adapter or webhook. | No integration exists to test. |
| 13 | Seven-chapter FIELDWORK Blueprint | **VERIFIED SANDBOX** | Existing supervised production path rendered the fictional Blueprint to PDF/PPTX with evidence ledger and commercial model. PDF SHA-256 `23c033a3f2a1...3827`; PPTX SHA-256 `c354be21de17...9449`. | 12.24 s successful render after one configuration retry. |
| 14 | Independent QA | **VERIFIED SANDBOX** | `independent-qa-report.json` returned `PASS_FOR_HUMAN_REVIEW`; checksum `fded19773efe...1415`. This is not human approval. | Same local run. |
| 15 | Immutable human approval blocks release | **VERIFIED SANDBOX** | `human-approval-checkpoint.json`: `status=pending`, `release_authorised=false`, `external_action_taken=false`; checksum `4f7093596783...c77a`. | Correctly blocked. |
| 16 | Creative territory and visual proof | **VERIFIED SANDBOX** | FIELDWORK includes the creative territory and the existing fictional illustration `built-for-the-work-of-living-v1.png`, SHA-256 `0f7812de5b5b...f39d`. | Local production only. |
| 17 | Campaign World → Creative Director's Bible → approved produced assets | **NOT TESTED** | No governed Campaign World/Bible approval chain or paid Higgsfield generation was run. Credentials are configured, but configuration is not execution; generation could spend money. | Requires explicit test scope and spend approval. |
| 18 | Activation preflight | **NOT WORKING** | Google Ads authenticated, exposed one account and a verified empty campaign list. Meta authenticated with 10 permissions but exposed zero businesses and zero ad accounts; campaign read failed without an account. TikTok is not configured. No publishing or spend occurred. | Live read-only probes. |
| 19 | Performance/iteration dashboard | **NOT TESTED** | No campaign was activated and no simulated performance dashboard was passed off as real. | Correctly stopped at preflight. |

## Failure and retry evidence

1. The first Tony safe-read marker contained `NO-SEND`. The conservative policy detected the word `send` and refused Gmail and Notion dispatch. The marker was changed to `ISSUE477-FICTIONAL-MARKER-ALPHA`; both live reads then passed with zero mutations. This is a safe fail-closed retry, not integration success for an arriving email.
2. The first FIELDWORK render failed because `NARRATIIVE_PRESENTATION_SKILL_DIR` points to a removed dependency version. A process-local path override produced the deck; production configuration was not changed. The stale configured path remains a blocker.
3. Tony's effective-tool inspection timed out at 30 seconds. A direct retry completed in 25.177 seconds and showed all tools. The diagnostic timeout is now 45 seconds. The later full acceptance exposed a separate real conversational failure that the old predicate missed.

## Idempotency and security

- The active inbound workflow visibly contains deduplication nodes, but duplicate execution was **not tested** because no production write was authorised.
- The live audit made zero external mutations and records only bounded counts, source identifiers and hashed provider record IDs.
- Runtime credentials remained in `~/.config/narratiive/runtime.env` with mode `0600`; no secret values were printed or persisted.
- All FIELDWORK artefacts were written to an isolated Issue #477 runtime/output path. The canonical Mac checkout and KatKin artefacts were not changed.

## Evidence files

- `live-integration-audit.json` — reproducible sanitized live-provider evidence.
- `tony-live-evidence.json` — Tony/OpenClaw run identifiers and the failed acceptance finding.
- `../issue-477-fieldwork/` — immutable fictional Blueprint, QA, ledger, render and approval artefacts.
