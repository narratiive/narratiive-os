# Tony OpenClaw Fleet Bootstrap

This change makes the managed OpenClaw bootstrap explicit and verifiable.

- Tony's canonical workspace now includes `AGENTS.md`, `IDENTITY.md`, `USER.md` and `SOUL.md` inside Narratiive OS.
- The fleet installer deploys those files with the five specialist workspaces.
- Live acceptance checks OpenClaw's own `agents list --json` runtime roster and requires Tony, Research, Strategy, Creative Director, Production and Operations to be visible.
- Research delegation/status turns fail when Tony reports spawn restrictions, a Tony-only roster or missing Research sessions.
- Narratiive OS remains the control plane for state, approvals, evidence, audit and deterministic consequences; OpenClaw remains the conversational and multi-agent runtime.
- The installer reads Matt's positive Telegram user ID from the mode-`0600`
  Narratiive runtime environment (`TONY_TELEGRAM_CHAT_ID`), registers it as an
  OpenClaw owner/approver, enables Telegram's native approval client in the
  originating chat, and forwards Narratiive plugin approvals for Tony's
  Telegram session. Gmail, calendar and other consequential writes still
  receive one exact, single-use approval; this configuration only makes that
  existing gate reachable.

The live Mac still requires the updated installer to be applied and the Gateway restarted before runtime acceptance can pass.

From the canonical checkout, apply the managed config and restart OpenClaw:

```bash
cd ~/Documents/narratiive-os
.venv/bin/python scripts/install_openclaw_fleet.py --apply
openclaw gateway restart
```

The installer fails closed when it cannot resolve a positive Telegram user ID.
It does not accept a Telegram group/supergroup chat ID as approval authority.
