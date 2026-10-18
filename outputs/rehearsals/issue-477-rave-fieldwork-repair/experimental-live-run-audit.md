# Rave founder-argument live execution audit

All runs used the frozen Rave research pack and `claude-sonnet-5`. No presentation production or external action occurred.

## Run v1 — blocked before quality review

- Outcome: `worker_retry_policy_exhausted`
- Cause: the new workflow was initially routed through the generic Claude return contract and exhausted its general output budget twice with `worker_output_truncated`.
- Repair: route the experiment through the bounded long-form budget and a dedicated return contract capped at 2,500 words.
- Evidence retained under `.runtime` in this rehearsal directory.

## Run v2 — correctly blocked by editorial QA

- Provider message: `msg_011Cg9h45wGhPX3EYUdDTpBJ`
- Outcome: `quality_failed:fieldwork_founder_argument_quality_gate`
- Passed: five-move sequence, commercial mechanism, no forecast claim, no repetition and no unsupported financial precision.
- Failed: evidence reference set used the top-level lineage as well as the nested basis; client specificity used “Rave” rather than the full “Rave Coffee” string; archived evidence contained the source phrase “value-led”.
- Repair: treat both governed lineage collections as the available evidence set, match the distinctive client-name token, and apply jargon review to founder-facing copy rather than quoted backstage evidence.
- The immutable failed candidate remains retained.

## Run v3 — accepted for human review

- Provider message: `msg_011Cg9hDhGoFhwkcU34gMtok`
- Accepted artefact checksum: `1206d70f92f3746378cab8d482131426d5cb23ee79335a900df88f1979a8f589`
- Outcome: `awaiting_approval`
- Editorial QA: every axis passed.
- Presentation production triggered: false.
- External action taken: false.

The accepted output is experimental and uses an archived public-evidence pack. It remains unsuitable for Rave contact or external presentation without current revalidation and human commercial review.
