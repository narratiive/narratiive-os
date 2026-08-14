# Narratiive Knowledge Repository Consolidation

Date: 2026-08-14

## Decision

Narratiive has one canonical repository: `narratiive/narratiive-os`.

The former `narratiive/narratiive-knowledge` repository is deprecated. Knowledge is a component of Narratiive OS and therefore lives under `knowledge/` inside the OS repository.

## Why

Maintaining separate operating-system and knowledge repositories created avoidable ambiguity for humans and agents. It increased the risk of duplicated doctrine, stale operational instructions, incorrect local paths and inconsistent judgements about which repository was authoritative.

## Migration policy

The old repository is not copied wholesale into Narratiive OS.

Material is classified before migration:

- Current reusable doctrine is curated into `knowledge/doctrine/`.
- Knowledge-governance rules are curated into `knowledge/governance/`.
- Narratiive-owned strategic IP belongs in `knowledge/handbook/`.
- Existing locked Growth Blueprint canon remains in `knowledge/blueprint/`.
- Current OS architecture, runtime code, workflows and agent contracts remain in their existing OS locations.
- Old runtime/OpenClaw instructions, duplicated root governance files and superseded architecture are retained only in the deprecated repository history and are not imported as active canon.
- Client-specific examples are migrated only when they remain necessary and do not duplicate newer OS workspace/client state.

## Retained material migrated in this consolidation

- Vision → `knowledge/doctrine/vision.md`
- Master strategic context → `knowledge/doctrine/master-context.md`
- Knowledge classification rules → `knowledge/governance/knowledge-types.md`
- Handbook namespace and model registry → `knowledge/handbook/README.md`

## Explicitly not promoted to active canon

The following categories from the old repository are not automatically migrated because Narratiive OS already contains newer or product-controlled equivalents:

- Root agent governance and decision-engine documents.
- OpenClaw/Tony runtime scripts and local startup instructions.
- n8n integration notes that pre-date the current OS runtime architecture.
- Growth Blueprint framework copies that would duplicate `knowledge/blueprint/manifest.json` controlled assets.
- Historical implementation sprints, handoffs and superseded roadmap/state documents.

They remain available in Git history for forensic reference until the old repository is archived.

## Agent rule

No agent may use `narratiive/narratiive-knowledge` to resolve a current strategic, product, runtime or architectural decision.

If information exists only in the deprecated repository, the agent must treat it as historical evidence and explicitly migrate or reconcile it into Narratiive OS before relying on it operationally.

## Local runtime note

Historical documents in the old repository reference local paths such as `~/Documents/narratiive-knowledge`. Those paths are retired. The canonical local checkout is defined in `AGENTS.md` as `~/Documents/narratiive-os`.

Any surviving LaunchAgent or local service still pointing to the retired checkout must be redeployed from the current Narratiive OS deployment scripts before the old local checkout is removed.

## Final state

Canonical GitHub repository: `narratiive/narratiive-os`

Canonical knowledge root: `knowledge/`

Canonical Narratiive IP/Handbook root: `knowledge/handbook/`

Deprecated repository: `narratiive/narratiive-knowledge`
