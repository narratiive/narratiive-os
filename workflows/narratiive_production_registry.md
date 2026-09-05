# Narratiive production workflow registry

`runtime.workflow_registry` is the executable source for Tony's principal
production workflow contracts. Every registered workflow declares inputs,
outputs, preferred capability, quality contract, retry policy, side-effect
classification, approval policy, next workflow, and fail-safe escalation.

The registered sequence is:

1. Growth Diagnostic → Blueprint Lite
2. Blueprint Lite → Discovery preparation
3. Discovery evidence → Growth Sprint proposal preparation
4. Growth Sprint → Research Engine
5. Research → Growth Blueprint
6. Growth Blueprint → Campaign World
7. Campaign World → Creative Director's Bible
8. Creative Director's Bible → creative asset production
9. Asset review → delivery preparation
10. Delivery → follow-up / next action preparation

These definitions describe internal orchestration and proposed handoffs. They do
not claim an integration or external action occurred. All automatic handoffs are
disabled until the execution coordinator proves the current step passed, the
next step is authorised, a valid worker exists, and no approval gate applies.
Client-facing drafts, meeting objectives, proposals, delivery packages, sends,
bookings, publications, and financial consequences remain human-gated.

The desired Blueprint Lite → Discovery journey is represented without changing
the existing `ClientLifecycleStage` ordering, which currently includes OUTREACH
between BLUEPRINT_LITE and MEETING. Resolving that lifecycle semantic remains a
reserved product/governance decision for Matt. The registry must not be used to
silently skip or rewrite that stage.
