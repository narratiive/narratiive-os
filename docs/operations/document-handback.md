# External document handback — bounded operational adapter

This adapter reuses WorkflowState, immutable workflow artefacts, the existing
signed exact-human manual-recovery gate and native Gmail adapter. It does not
run a specialist, approve an upload, advance a subsequent workflow or send mail.

1. Ask Tony for `document_brief` on an exact engagement run. Fieldwork references
   the active Drive v7.0 specification and discovered original Rave benchmark;
   the brief retains strategy identity, evidence, constraints and missing deadline.
   No Sketchbook design standard is asserted.
2. Use `register_document` with exact workspace/client/run, title, producer,
   version and `files` mapped to stage fields. Files contain either bounded
   `content_base64` or a verified stored Drive `drive_file_id`. Native Google
   files must first be exported; this adapter does not mutate originals.
3. Registration is currently permitted only at an already blocked **final
   preparation stage** supported by existing manual recovery. Fieldwork requires
   a PDF and editable PPTX plus its complete stage-output bundle. The adapter may
   reuse a checksum-verified persisted failed candidate's bundle, or accept a
   specialist-supplied complete bundle. It cannot invent missing outputs, replace
   upstream strategy/governance fields or skip later quality stages.
4. Tony returns an immutable candidate, exact file checksums/provenance and a
   `manual_recovery` envelope. Matt must review the actual document and explicitly
   authorise that exact manual recovery through the existing signed operation.
   Upload alone records neither approval nor quality acceptance. The adoption is
   labelled manual/non-automated; original failures and versions remain retained.
5. `prepare_document_draft` with its exact `candidate_id` requires that recorded
   human decision. It creates an **unsent internal-review draft** to the existing
   authorised internal address only, reads it back and verifies recipient, subject,
   body and attachment hashes. It records a real draft receipt; no send operation
   is exposed by this adapter. Real-client delivery still requires the separate
   exact-message/attachment approval and verified recipient boundary.

Telegram control-plane operations: `document_brief`, `register_document`, existing
`manual_recovery`, `prepare_document_draft`. Slash equivalents are
`/document-brief <exact-run>`, `/handback <exact-run>` and
`/draft-document <exact-run>` with structured tool inputs. Approvals use the
existing trusted-turn proof, never a model-composed human instruction.

Unsupported current stages (including multi-stage Campaign World generation),
missing commercial/quality fields, absent verified recipients and absent booking
links remain explicit blockers. Booking, acceptance and payment monitoring are
not added by this adapter. An email or user assertion is not settlement evidence.

For a Fieldwork commission, request the exact approved Fieldwork presentation run,
not its original diagnostic root. The command does not substitute another run.
Its founder-facing response is one complete copyable Claude brief; the detailed
`specialist_audit` retains exact identities, approval evidence, strategy, source
register, assumptions and expected output keys. Fictional rehearsal approval is
labelled separately from Matt/client approval. Fieldwork v7 includes the v7.2
operating addendum in the linked canonical specification. Oversized or incomplete
records return an explicit blocker instead of a truncated commission. An asset
review folder is not evidence of an available Fieldwork working destination.
