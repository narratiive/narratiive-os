# Narratiive client journey naming canon v1.0

Status: APPROVED PRODUCT CANON
Version: 1.0.0
Decision: Matt, 22 October 2026
Owner: Narratiive / Matt

## Customer-facing journey

The approved customer-facing journey is:

`Growth Diagnostic → Groundwork → Discovery → Proposal → Fieldwork → Sketchbook → Activation`

| Customer-facing name | Existing implementation | Customer promise |
| --- | --- | --- |
| `Groundwork` | Blueprint Lite pre-sales assessment | A concise, personalised assessment that combines the completed Growth Diagnostic with selective outside-in research and prepares an informed Discovery conversation. It is not the paid strategic product. |
| `Fieldwork` | The paid strategic engagement that produces the approved Growth Blueprint | Evidence-led research, strategic synthesis, strategy development and an approved Growth Blueprint. |
| `Sketchbook` | The existing Campaign World and Creative Director's Bible creative-strategy and development path, with governed illustrative asset preparation where authorised | A strategy-grounded creative direction, distinct concepts and a coherent review package. It does not itself authorise production, publication or delivery. |
| `Activation` | Downstream campaign execution, production, delivery and performance operation | Execution after the relevant strategy, creative, production and external-action approvals. Activation is outside the client-journey certification approved on 22 October 2026. |

`Growth Diagnostic`, `Discovery` and `Proposal` retain their existing customer-facing meanings.

## Compatibility contract

- This is a customer-facing naming layer, not a workflow redesign.
- Existing workflow IDs, stage IDs, lifecycle values, persisted labels, artefact types, schemas, templates and historical records remain unchanged.
- `Blueprint Lite`, `Growth Sprint`, `Growth Blueprint`, `Campaign World`, `Creative Director's Bible`, `Production Pack`, `Asset Manifest` and `Performance Feedback` remain valid internal or artefact names where their established contracts require them.
- Groundwork does not expand Blueprint Lite into the paid Growth Blueprint.
- Fieldwork names the paid strategic engagement; Growth Blueprint remains the strategic artefact produced within it.
- Sketchbook groups the existing governed creative-development path; it does not collapse or rename Campaign World, Creative Director's Bible, Production Pack or Asset Manifest internally.
- Activation never inherits approval from Fieldwork or Sketchbook. Production, external delivery, publication, media mutation and spend keep their existing exact-version and external-action gates.
- Existing records are not migrated or rewritten. New customer-facing copy uses the approved names while internal identifiers preserve backward compatibility.
- The separate FIELDWORK v4 and SKETCHBOOK v2 development branches remain separate until their own pull requests, reviews and approvals are complete.

## Change log

### 1.0.0 — 22 October 2026

- Recorded Matt's customer-facing names for Groundwork, Fieldwork, Sketchbook and Activation.
- Bound each name to the existing implementation without changing workflow identity, history, specialist ownership or approval authority.
- Kept Activation outside the scope of the client-journey certification.
