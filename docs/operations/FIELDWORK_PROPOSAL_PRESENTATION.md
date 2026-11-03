# FIELDWORK proposal presentation contract

`runtime.fieldwork_proposal_pdf.FieldworkProposalDraft` is the fixed, two-page
A4 presentation contract for a Narratiive FIELDWORK proposal. It is a derived
review artefact, never a replacement for the canonical structured proposal or
its evidence lineage.

The layout has these bounded fields: client identity; headline and introduction;
one commercial hypothesis; an optional, evidence-bound opportunity metric; three
insights; three deliverables; closing statement; timeline; approved investment;
focus; and supplied visual assets. Copy is clipped at editorial limits rather
than reduced below readable type.

Before a proposal renders, `FieldworkProposalQualityGate` requires two
checksum-addressed assessment records, each bound to the exact proposal source
and resolved from append-only workflow history:
one from the Strategy Director (business specificity, commercial relevance,
evidence quality, insight distinctiveness and commercial proposition) and one
from the Creative Director (headline, copywriting, visual hierarchy, brand
expression and editorial quality). Each record carries the named specialist,
an immutable assessment-artifact reference, recorded time, criteria and its
own canonical checksum. The newest exact-source assessment for each role
controls; a stale pass cannot override a later revision. Bare `pass` maps are
invalid. The referenced assessment artefact must resolve in persisted workflow
lineage, with matching bytes and checksum. The render input must likewise
match the checksummed authoritative proposal source. Each rendered strategic
insight must also cite a non-empty source identifier within the authoritative
Discovery or GROUNDWORK lineage. Known placeholder copy and repetitive,
insubstantial insights fail closed.

The renderer can only produce a client quotation or released presentation when
`proposal_evidence_readiness.client_facing_ready` is true and the exact
checksum-bound FIELDWORK fee approval is present in `commercial_context`.
Where the evidence is ready but no fee has been approved, it may produce only
a clearly marked internal founder-review draft that states the investment is
to be agreed; it cannot be released, emailed or treated as a quotation. Only
`HumanReviewPresentationService` may invoke the PDF renderer after it has
checked the persisted source, evidence and specialist records; the renderer's
public entry point rejects ungoverned preview rendering.

Every monetary opportunity needs source references, a calculation basis and a
confidence/limitation record in the canonical proposal evidence. The visible
PDF may show only the concise client-language result. The renderer never
calculates a fee, never publishes a range, and never writes client data back to
the workflow.

Visual assets are supplied with the presentation request and must retain their
asset lineage outside the visible document. A missing or unverified image uses
a neutral visual placeholder in review output; it must not be silently replaced
with a stock or generated image.
