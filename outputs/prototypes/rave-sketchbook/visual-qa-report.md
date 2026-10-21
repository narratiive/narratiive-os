# Rave SKETCHBOOK visual QA report

Status: **PASS FOR INTERNAL REVIEW / NOT CLIENT APPROVED**

Artefact: `INTERNAL-Rave-SKETCHBOOK-canonical-prototype-v2.pptx`

Review copy: `INTERNAL-Rave-SKETCHBOOK-canonical-prototype-v2.pdf`
Pages inspected: 5 of 5

## Automated checks

- Package integrity: **PASS** — five slides, no package findings.
- Layout geometry: **PASS** — 16:9 canvas, no overlap or out-of-bounds findings.
- Heading fit: **PASS**.
- Font policy: **PASS** — Arial used throughout; native text remains editable.
- PDF conversion: **PASS** — five pages, 960 × 540 pt page size.

The private validation receipt is retained outside the committed output folder at
`.presentation-build/presentation-validation-v2.json`.

## Page-by-page visual inspection

| Page | Canonical type | Result | Review notes |
| --- | --- | --- | --- |
| 1 | Creative proposition | PASS | Immediate proposition, strong Rave yellow/ink contrast, readable supporting promise, hero visual carries the shared FIELDWORK path motif. |
| 2 | Audience profile | PASS WITH HUMAN VALIDATION GATE | Portrait and hierarchy are clear. The audience remains visibly labelled as a source hypothesis, preventing the design from implying verified customer research. |
| 3 | Visual world and art direction | PASS | Warm domestic setting, product legibility, Rave Yellow and anti-reference guidance read as one coherent visual system. |
| 4 | Campaign territory | PASS | The Anti-Snob construction is distinctive, repeatable and understandable without presenter explanation. Comparative language still requires product/legal review before use. |
| 5 | Campaign executions and applications | PASS WITH OPERATIONAL GATE | Three channel applications feel related without being duplicates. Timestamp and quiz journey are explicitly labelled illustrative/unverified. No live activation is implied. |

## Template-system checks

- Exactly five canonical page types: **PASS**.
- Editable native text: **PASS**.
- Rave Yellow on every page: **PASS**.
- Minimum type size: **PASS** for intended review rendering.
- Image crops and focal points: **PASS**.
- Meaningful image alt text: **PASS**.
- Visible INTERNAL / NOT CLIENT APPROVED state: **PASS**.
- Speaker-note provenance and evidence status: **PASS**.
- Missing/overflow behaviour defined in machine-readable specification: **PASS**.
- Live-media or performance implication: **PASS — none**.

## Remaining human judgement

1. Matt must decide whether `Serious coffee. Zero snobbery.` remains the desired
   creative north star for the current Rave exercise.
2. Product/legal review is required before external use of comparative lines
   such as `Tasting notes: theatre. Roast date: everything.`
3. Rave first-party evidence is required before treating The Upgrader as a
   validated audience, publishing delivery timestamps, or asserting a current
   quiz path.
4. Client-facing release still requires the exact-version human approval record.

No production system, campaign, media account, customer communication or
client deliverable was changed or released during this QA pass.
