# Tony OpenClaw Fleet Bootstrap

This change makes the managed OpenClaw bootstrap explicit and verifiable.

- Tony's canonical workspace now includes `AGENTS.md`, `IDENTITY.md`, `USER.md` and `SOUL.md` inside Narratiive OS.
- The fleet installer deploys those files with the five specialist workspaces.
- Live acceptance checks OpenClaw's own `agents list --json` runtime roster and requires Tony, Research, Strategy, Creative Director, Production and Operations to be visible.
- Research delegation/status turns fail when Tony reports spawn restrictions, a Tony-only roster or missing Research sessions.
- Narratiive OS remains the control plane for state, approvals, evidence, audit and deterministic consequences; OpenClaw remains the conversational and multi-agent runtime.

The live Mac still requires the updated installer to be applied and the Gateway restarted before runtime acceptance can pass.
