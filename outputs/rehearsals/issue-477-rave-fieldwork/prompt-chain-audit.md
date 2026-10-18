# FIELDWORK Rave prompt-chain audit

Date: 17 October 2026

Scope: internal unsolicited strategy exercise; Rave Coffee was not contacted.

Decision: do not rebuild the system. Add one argument gate before the existing structured production and rendering stages.

## Executive finding

Strategic quality deteriorates at the first schema-heavy Tony commission, before presentation production.

The direct Claude commission and Tony commission used the same frozen research pack, the same Anthropic provider and the same `claude-sonnet-5` model. The direct route was asked to make one cumulative five-slide founder argument. Tony's retained `research_to_growth_blueprint` route asked the model to complete a large set of parallel diagnosis, implication, uncertainty, choice and lineage fields. The Tony response is careful and evidence-rich, but it reads as a strategic database: it is 3,430 words versus 1,880 for the direct response, repeats the same caveats across sections, and never has to prove that its opening five moves form one persuasive argument.

The renderer is not the cause. It faithfully turns the structured fields into repeated slide patterns and therefore magnifies an upstream editorial problem. The independent review catches the weakness after production, but does not rewrite the argument.

## Chain inspection

| Stage | What happens now | Observable consequence |
|---|---|---|
| Research | Six archived public-evidence files are assembled with source IDs and caveats. | Evidence discipline is materially stronger than the historic Claude benchmark, but the pack is frozen at 6 September 2026 and must be revalidated before external use. |
| Commission | `runtime/workflow_instructions.py` tells the retained route to fill eight strategic sections, choices, uncertainties and lineage. | Completeness becomes the model's dominant job; editorial selection becomes secondary. |
| Context handoff | `runtime/workflow_execution_coordinator.py` promotes a bounded allow-list of strategy context. | Optional nuance can be lost, while the surviving material is organised around schema fields rather than an argument. |
| Model dispatch | `runtime/tony_claude_api_dispatcher.py` sends one user message, JSON context and an additional Blueprint length constraint. | The model receives no separate senior-editor system role and is rewarded for contract compliance. |
| Contract | The retained route returns the older field set. Current `growth_blueprint_quality_gate` expects `central_thesis`, `narrative_progression`, `editorial_judgement`, `contradiction_resolution`, `quantitative_evidence_treatment`, `assumption_control` and `completeness`. | The live comparison returned `recommendation: advance` while all seven current gate fields were absent. This is a contract mismatch, not a subjective presentation complaint. |
| Independent review | The historic Rave review scored coherence 2/5, commercial consequence 2/5 and non-obviousness 2/5. | The review correctly identifies the problem, but only after the weak argument exists. |
| Presentation | `runtime/growth_blueprint_deliverable_worker.py` converts structured sections into a deterministic presentation spec and renderer. | Repeated section anatomy becomes repeated slides; visual polish cannot recover a missing thesis. |

## Controlled comparison

Execution record: `comparison-execution.json`. Both calls completed with `stop_reason: end_turn`; neither triggered an external action.

- Identical research pack SHA-256: `71771f5bfdabb0da52f67ff5bd19d89d4721bf78287c4168f7d88b098bd66428`
- Direct Claude message: `msg_011Cg7rhd9KWjTrMYHqkJhUd`
- Tony route message: `msg_011Cg7rqynkveDqDMnUjhFnd`
- Provider/model: Anthropic / `claude-sonnet-5` for both

The direct commission produced a cumulative opening with a visible sequence: position, opportunity equation, prioritised levers, audience hypothesis and direction. The Tony route produced stronger granular lineage, but dispersed the decision across market, audience, barriers, difference, positioning, narrative, opportunity, activation and four choices. Its most commercially forceful idea appears repeatedly in different words rather than becoming the controlling argument.

## Historic Claude benchmark: what to keep and what not to copy

The original Claude-generated Rave Blueprint and Campaign World are stronger at editorial confidence, memorable positioning and creative ambition. “De-snobbed speciality” gives the founder a clear organising thought and the Campaign World demonstrates how strategy could become culturally visible.

They are not a safe evidence standard. The historic work contains market and audience assertions that are not always traceable, and the Campaign World introduces arbitrary 60/30/10 allocation and performance targets without Rave's commercial baseline. Those should remain creative hypotheses, not be promoted to forecasts or investment recommendations.

## Smallest effective repair

Add a mandatory five-slide argument gate between research synthesis and full FIELDWORK schema/rendering:

1. Current position — the consequential truth the founder should recognise.
2. Credible 12-month opportunity — a transparent lever model populated only with verified client data.
3. Growth levers — prioritised, sequenced and explicit about trade-offs.
4. Audience opportunity — a testable commercial hypothesis, not a decorative persona.
5. Strategic direction — one earned choice, in plain English.

Each slide must contain evidence, insight, commercial implication and decision, and must add something not already said. A founder-value review should fail the gate if a competitor's name can be substituted without changing the argument, if a claim lacks a classification, or if the commercial opportunity depends on an invented number.

Keep the full evidence and lineage schema backstage. Only expand into the seven-chapter FIELDWORK deliverable after the argument passes. Route new work through the canonical thesis/director path and fail closed on the retained legacy route until its contract matches the current quality gate. No orchestrator or renderer rebuild is required.

## Approval boundary

This repair changes the product commission and acceptance gate, so it should be reviewed by Claude Code against the product specification and approved by Matt before becoming the default client workflow. The five-slide review deck is an experiment, not a released Rave deliverable.
