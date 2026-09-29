# Narratiive service supervisor

`python scripts/service_supervisor.py` runs the repository service doctor and applies a narrow restart policy to the unhealthy component only.

## Configuration

Commands are JSON argument arrays. They are executed directly without a shell.

```bash
export NARRATIIVE_RUNTIME_RESTART_COMMAND='["launchctl","kickstart","-k","gui/501/com.narratiive.runtime"]'
export TONY_BRIDGE_RESTART_COMMAND='["launchctl","kickstart","-k","gui/501/com.narratiive.tony-http-bridge"]'
export NARRATIIVE_SUPERVISOR_EVENT_LOG="$HOME/Library/Logs/Narratiive/supervisor.jsonl"
python scripts/service_supervisor.py
```

Optional settings:

- `NARRATIIVE_DOCTOR_COMMAND`: override the default `python3 scripts/service_doctor.py` command.
- `NARRATIIVE_DOCTOR_PROCESS_TIMEOUT_SECONDS`: service doctor process timeout; default 15 seconds.
- `NARRATIIVE_RESTART_TIMEOUT_SECONDS`: timeout per restart command; default 20 seconds.
- `NARRATIIVE_SUPERVISOR_EVENT_LOG`: append-only JSON Lines event log.

The supervisor decodes both service health and deployment-receipt state. It
restarts only the unhealthy service components for doctor codes `10`, `20`,
`30`, `50`, `60`, or `70`. A deployment-only failure (`40`) does not restart a
healthy service. Codes containing the deployment bit remain
`deployment_action_required` with exit `1` after any safe service recovery,
because a restart cannot reconcile an undeployed repository revision.
Unsupported doctor exit codes are rejected rather than interpreted as a
restart instruction.
