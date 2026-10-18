# Issue 477 reliability rollback

Scope: Gmail inbox watcher, Gmail draft creation, Tony specialist resumption and the contract/payment sandbox boundary.

This branch does not deploy any service. The following procedure applies only after a separately authorised deployment.

## Source rollback

1. Identify the last approved reliability commit and the exact deployed revision from the deployment receipt.
2. Revert the focused reliability commit with a new Git commit. Do not rewrite or force-push history.
3. Run the full runtime test suite and obtain independent review against the revert commit.
4. Deploy only through the canonical `scripts/deploy_narratiive_os.sh` entry point after separate production authorisation.

## Gmail watcher rollback

1. Preserve the watcher state and deployment receipts before any change.
2. Restore the previously backed-up LaunchAgent property list described in `GMAIL_WATCHER_PASS2_DEPLOYMENT.md`.
3. Reload only the Gmail watcher LaunchAgent. Do not restart unrelated Narratiive services.
4. Verify that no duplicate draft or outbound message was created. A manual invocation does not prove unattended recovery.

## Gmail OAuth rollback

The added compose permission authorises draft creation as well as message composition. If that access is no longer acceptable, revoke the Google Workspace token, reauthorise without `https://www.googleapis.com/auth/gmail.compose`, and verify that read-only inbox monitoring still works. Existing drafts remain in Gmail and must not be deleted automatically.

## Tony asynchronous-return rollback

Revert the gateway repair and reload only the Tony bridge after separate deployment authorisation. Preserve every existing execution journal and run artefact. Confirm that queued work is visible before and after rollback; never mark an interrupted specialist run complete by inference.

## Commercial sandbox rollback

The commercial-close boundary has no live payment or signature adapter. Reverting it removes only the synthetic boundary and its tests. It must not cancel, create or amend any real commercial agreement.
