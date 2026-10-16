# Gmail watcher — Production Readiness Pass 2 deployment

This change is not authorised for production until Matt explicitly approves it.

## Observed pre-deployment state

- Loaded label: `com.narratiive.gmail-inbox-watch`
- Canonical checkout: `~/Documents/narratiive-os`
- `RunAtLoad=true`, `StartInterval=900`, `KeepAlive=false`
- launchd reported `runs = 0` and no recorded exit for the current load
- retained logs contain two older successful no-new-mail runs
- the production plist and secure environment file contain no inline secrets

## Exact bounded deployment

1. Preserve the current plist bytes and current `launchctl print` output.
2. Confirm the reviewed PR #478 watcher code exists in the canonical checkout.
   Do not deploy from another checkout and do not merge the pull request as part of
   this operation.
3. Render and validate only `com.narratiive.gmail-inbox-watch` with:

   ```bash
   cd ~/Documents/narratiive-os
   .venv/bin/python scripts/install_launch_agents.py \
     --python .venv/bin/python \
     --env-file "$HOME/.config/narratiive/runtime.env" \
     --only com.narratiive.gmail-inbox-watch
   ```

   The installer writes atomically, reloads only that label, and restores the
   previous plist if bootstrap fails. It does not reload the runtime, Tony bridge,
   conversation worker, supervisor or proactive brief agents.
4. Use a unique controlled marker and exact Gmail query. The test message must be
   between explicitly authorised Narratiive-owned accounts. No prospect address is
   permitted.
5. Verify the RunAtLoad execution from launchd run count, structured stdout, Gmail
   message ID, n8n execution, Notion record and Telegram receipt. Replay the same
   marker and verify deduplication.
6. Make no manual invocation for the next 15 minutes. Verify that launchd increments
   the run count and appends a fresh successful result. This second run is the
   unattended proof.
7. On any non-zero exit, wrong target, duplicate external write or missing audit
   evidence, boot out the new label, restore the preserved plist, bootstrap it and
   record the failure without retrying external mutations.

