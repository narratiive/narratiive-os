# Rave SKETCHBOOK canonical prototype

Status: **INTERNAL / NOT CLIENT APPROVED**

This folder contains a five-page, client-facing SKETCHBOOK prototype built from
the original `NOS-CAMPAIGNWORLD-RAVE-v3` source. It demonstrates the five
canonical page types as finished examples rather than as wireframes:

1. Creative proposition
2. Audience profile
3. Visual world and art direction
4. Campaign territory
5. Campaign executions and applications

The PowerPoint is the editable review source. The PDF is the fixed review copy.
`template-specification.json` is the deterministic population contract for Tony.
The source document itself is not committed; its Drive ID and checksum are
recorded in `source-provenance.json`.

All portraits, product scenes and campaign applications in this prototype are
creative illustrations. They do not depict verified customers, current Rave
packaging, live media, operational service levels or approved client work.

## Rebuild

Run the build with the bundled presentation runtime described by the repository
presentation tooling. The builder creates the editable `.pptx`, per-slide PNGs,
an integrity/layout validation receipt and a render receipt. PDF conversion is
performed separately so the review copy can be inspected page by page.
