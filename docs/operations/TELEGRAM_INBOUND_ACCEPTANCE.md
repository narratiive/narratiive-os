# Telegram inbound acceptance check

After publishing the workflow and restarting the managed n8n and tunnel
LaunchAgents:

1. Send a harmless unambiguous conversational request, such as
   `Tony, please reply with a short hello so I can confirm you can hear me.`
2. Confirm a new successful execution for workflow `s7TvzzAsJRKLRDU7`.
3. Inspect that execution and record the transition evidence:
   Telegram Trigger update and message IDs; successful authenticated HTTP
   Request; Tony bridge `runtime: openclaw`; non-empty OpenClaw response;
   formatter output; and successful Telegram Send message ID.
4. Confirm the exact bot reply appears in the originating Telegram chat.
5. Confirm the bridge access log contains a `200` request to
   `/telegram/inbound`, and the OpenClaw session contains the matching user and
   assistant turns.
6. Restart both ingress LaunchAgents. Confirm the workflow activates again, the
   Telegram webhook still owns the stable HTTPS n8n URL, and the accepted
   message is not replayed.

For the attention acceptance, use only a uniquely named explicit SAFE fixture.
Capture all non-fixture attention state before the test, ask Tony to use
`narratiive_manage_attention` on the fixture ID, and verify:

- the OpenClaw session contains the tool call and successful tool result;
- the bridge records `POST /attention/control` with HTTP 200;
- one append-only event changes only the fixture and reports
  `external_action_taken: false`;
- all non-fixture attention state is byte-for-byte or hash-equivalent; and
- Tony's Telegram reply describes only the fixture operation.

Do not use genuine leads for this test and do not treat Tony's prose alone as
execution evidence.
