# Issue #477 — GO / NO-GO decision

## Decision

**NO-GO for accepting a paying customer into an end-to-end automated journey.**

**Conditional GO for a supervised integration rehearsal only** after Matt supplies the controlled accounts and explicitly approves the bounded synthetic writes listed below.

## P0 blockers

| Blocker | Evidence | Required action | Owner |
|---|---|---|---|
| No controlled Gmail arrival/recipient | Gmail is live for reads, but the fictional marker returned zero and no message was sent. | Supply a controlled external test mailbox and approve one labelled synthetic inquiry, proposal send and acceptance reply. | Matt / Operations |
| Gmail watcher has not run | Loaded LaunchAgent reports zero runs; logs are stale. | Approve production-safe kickstart/redeploy, observe one interval, then prove message ID → webhook execution. | Matt approval; Codex executes |
| No Notion/Telegram write evidence | Both connectors read/probe successfully; no lifecycle write was authorised. | Approve one isolated synthetic Notion lead and one internal Telegram notification, then replay to prove deduplication. | Matt / Operations |
| No consented Fireflies meeting | Fireflies access is live but transcript list is empty. | Hold and record a consented fake discovery call; capture transcript-ready time and follow-up-draft latency. | Matt / Operations |
| Tony customer handoff failure | Live contextual action returned no response; legacy acceptance falsely passed it. | Diagnose OpenClaw contextual-action/session behaviour. The branch already prevents this output from passing acceptance. | Codex / OpenClaw owner |
| Contract/payment stage absent | No sandbox contract or payment connector exists. | Select sandbox provider/event contract or explicitly retain a human attestation gate; never represent it as payment verification. | Matt / Commercial / Codex |
| Creative chain not executed | Creative territory and proof exist locally; Campaign World, Bible approval and provider asset generation were not run. | Approve a bounded sandbox creative brief and any generation cost, then record provider task IDs, QA and exact-version approval. | Matt / Creative Production |
| Activation incomplete | Google read works; Meta has no delegated assets; TikTok is unconfigured. | Assign a Meta test business/ad account, configure TikTok test advertiser access, and rerun read-only permission/account/campaign preflight. | Matt / Media Operations |
| Presentation runtime path stale | Configured presentation skill directory no longer exists. | Update the production runtime environment to the installed dependency version and restart only after approval. | Matt approval; Codex executes |

## Exit criteria for GO

One new trace must prove, with provider IDs and timestamps:

1. controlled Gmail receipt;
2. one deduplicated n8n execution;
3. one synthetic canonical Notion lead and Tony projection;
4. one Telegram notification;
5. a consented Fireflies transcript and follow-up draft within the measured target;
6. exact approval before Gmail proposal send and verified recipient acceptance;
7. explicit contract/deposit sandbox state;
8. FIELDWORK production, independent QA and checksum-bound Matt approval;
9. Campaign World/Bible/sample-asset approval;
10. Meta, TikTok and Google delegated-access preflight stopping before launch or spend.

Until those events exist, a passing unit suite, configured credential, generated deck or simulated workflow does not change the decision.
