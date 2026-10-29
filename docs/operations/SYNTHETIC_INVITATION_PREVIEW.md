# Synthetic discovery invitation preview

Issue #500's trusted-owner follow-up authorises this bounded preparation only.
The unmerged founder journey contract is not a prerequisite. Owning stream:
Worker Infrastructure; downstream consumer: the founder's external-send review.

`runtime.synthetic_invitation_preview.build_invitation_preview` returns an
internal in-memory email preview and exact-content SHA-256 approval digest.
It does not send, schedule, contact providers, create a prospect, persist private
values, or record approval. No live integration has been verified by this change.

The permanent Discovery-invitation default is a warm, concise conversation:
**THE BIGGER AMBITION**, **THE PEOPLE WHO MATTER**, and **WHAT MAKES YOU
UNMISSABLE**. Each section requires one validated GROUNDWORK observation and
one question, with its internal source reference retained only in the approval
material. The renderer fails closed unless all three are present; it never
manufactures company-specific copy.

The authorised Loom Loft rehearsal (`inbound-d1b96a67`) is the sole exception:
it uses the founder-approved fictional copy exactly as approved. That copy is
explicitly isolated from all other entities; real-prospect invitations remain
evidence-bound and must be personalised from verified research.

Call with an explicit `workspace_id` and a private configuration mapping, or omit
`config` to resolve environment values at call time. Required keys share the
`NARRATIIVE_SYNTHETIC_INVITATION_` prefix:

| Suffix | Private configuration value |
| --- | --- |
| `WORKSPACE_ID` | Exact caller workspace identifier |
| `RECIPIENT` | Founder-designated synthetic external test mailbox; no default |
| `GMAIL_SENDER` | Exact authorised Gmail sending identity; no default |
| `SENDER_AUTHORITY_REF` | Non-secret reference to sender authorisation |
| `BOOKING_URL` | Authorised HTTPS booking page offering a 30-minute call |
| `BOOKING_AUTHORITY_REF` | Non-secret reference to booking-page authorisation |
| `COMPANY_NAME` | Exact synthetic prospect/company label shown in the preview |
| `ENTITY_ID` | Exact safe workflow entity identifier |
| `DISCOVERY_PREPARATION_REF` | Exact existing Discovery Preparation artefact reference |
| `MEETING_DURATION_MINUTES` | Must be `30` for this founder-approved invitation path |

Keep these values in private runtime configuration outside Git (mode `0600`
for an environment file). Do not put credentials in authority references or
booking links. Links with user credentials, query strings or fragments are
rejected. The synthetic recipient is never an internal review destination or
public default. This capability neither reads nor modifies the internal-review
delivery configuration.

Example invocation inside an authorised internal Python caller:

```python
from runtime.synthetic_invitation_preview import build_invitation_preview

preview = build_invitation_preview(workspace_id="synthetic-test")
```

The return value contains private addresses: display it only to the authorised
internal reviewer; do not log it or commit generated output. Missing or invalid
configuration returns named blockers and no email/digest. Supplied authority
references are configuration assertions, not independently verified evidence.
The booking-page route avoids inventing available slots.
Control characters are rejected before trimming configuration whitespace. The
email preview is a separate display copy: editing it does not change the digest's
email snapshot. Callers must regenerate the preview after configuration changes;
neither returned dictionary is an approval record or a tamper-proof store.

Founder action: confirm the sender authority and that the configured booking
page offers the intended 30-minute call; review the exact From, To, subject and
body; authorise **one** external synthetic invitation for the displayed checksum
through the existing authenticated single-use approval boundary. Any change
requires a new preview and approval. The digest is a review reference, not an
approval token. This module cannot consume approval or send even after approval;
a separately authorised execution step must preserve the existing approval and
verified Gmail receipt conventions. Google Meet transcript and Gemini notes are
the intended future evidence source; Fireflies remains an optional fallback.
Calendar, transcript ingestion, proposal and FIELDWORK execution remain outside
this increment.

Validation: ` .venv/bin/python -m unittest discover -s tests -p 'test_synthetic_invitation_preview.py' -v`

Independent technical review remains required; founder approval of the exact
email remains separate from code review. No migration or existing dispatch
contract changes are introduced.
