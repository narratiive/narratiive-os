# Strategic Synthesis and Strategy Thesis

**Status:** Canonical internal product contract  
**Version:** 1.0  
**Decision date:** 29 September 2026

## Purpose

Strategic Synthesis and Strategy Thesis are the governed internal bridge between
Research and the Narratiive Growth Blueprint. They make the evidence-to-strategy
decision boundary explicit without changing the external Growth Sprint journey
or creating another client-facing product.

The canonical internal sequence is:

`Research → Strategic Synthesis → Strategy Thesis → Growth Blueprint`

Both artefacts belong to the Strategy Director. Tony orchestrates their runs,
lineage, review presentation and approval state; Tony does not author, approve
or silently rewrite their strategic content.

## Strategic Synthesis

Strategic Synthesis organises the approved research evidence before a strategic
choice is proposed. It is an internal preparation stage and is not itself a
human approval gate.

It must contain:

- an executive synthesis, commercial problem, growth opportunity and material
  implications;
- a commercial growth equation covering ambition, current state, growth gap,
  growth logic, levers and assumptions;
- evidence-linked patterns and strategic tensions;
- explicit contradictions, research gaps and open inputs;
- claim-level fact, interpretation and hypothesis classification; and
- complete source and parent-artefact lineage.

Strategic Synthesis may recommend progression, further research or stopping. It
cannot approve a strategy, suppress uncertainty, contact a client, release an
artefact or perform any external action.

## Strategy Thesis

The Strategy Thesis converts a quality-accepted Strategic Synthesis into one
coherent proposed strategic answer. It must make the choices and trade-offs that
will control the Growth Blueprint explicit.

It must contain:

- a thesis statement;
- commercial ambition and growth equation;
- priority audience and category choice;
- source of difference and positioning choice;
- narrative platform, growth opportunity and activation principles;
- evidence-linked strategic choices and trade-offs;
- a decision register whose owner remains Matt;
- evidence limits, uncertainty and open questions; and
- complete source, synthesis and research lineage.

## Gate 3

Strategy Thesis is the exact-version **Gate 3** human review artefact. Matt must
approve, request revision or stop the exact immutable Strategy Thesis checksum.
A quality result, Tony recommendation, completed run or delivered review copy is
not approval.

Only an approved Strategy Thesis may enter the canonical
`strategy_thesis_to_growth_blueprint` workflow. That handoff binds the exact
Strategy Thesis artefact ID, version and checksum and carries its Strategic
Synthesis and evidence pack forward. The Growth Blueprint may elaborate the
approved thesis but must not contradict or silently broaden its strategic
choices.

Approval remains internal-product approval. It does not authorise client
release, presentation export, creative production, publication, media spend or
any other external action.

## Compatibility

Persisted historical `research_to_growth_blueprint` runs remain readable and
resumable so immutable history is not discarded. New canonical handoffs do not
target that legacy route.

## Version history

- **1.0 — 29 September 2026:** Established the evidence-only Strategic
  Synthesis, exact-version Strategy Thesis Gate 3, and approved-thesis handoff
  into Growth Blueprint production.
