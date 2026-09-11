import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { buildActionProposal } from "./action-policy.js";
import { buildNativeApprovalRequirement, buildWorkflowApprovalRequirement } from "./approval-policy.js";
import { executeApprovedAction } from "./execution-client.js";
import { executeSafeRead } from "./safe-read-client.js";
import { resolveBridgeToken } from "./bridge-auth.js";

const DEFAULT_URL = "http://127.0.0.1:8790/control-plane";
const DEFAULT_CONTROL_PLANE_TIMEOUT_MS = 8000;

function schema(properties = {}, required = []) {
  return { type: "object", properties, required, additionalProperties: false };
}

const ACTION_SCHEMA = {
  action: { type: "string", minLength: 1, maxLength: 4000 },
  surface: { type: "string", enum: ["research", "strategy", "creative", "production", "gmail", "calendar", "notion", "drive", "github", "n8n", "replit", "other"] },
  kind: { type: "string", enum: ["read", "prepare", "write"] },
  target: { type: "object", additionalProperties: true },
};

const SAFE_READ_SCHEMA = {
  action: { type: "string", minLength: 1, maxLength: 4000 },
  surface: { type: "string", enum: ["gmail", "calendar", "notion", "drive", "github", "n8n", "replit"] },
  kind: { type: "string", enum: ["read"] },
  target: { type: "object", additionalProperties: true },
};

const STATE_READ_SCHEMA = {
  view: { type: "string", enum: ["executive_brief", "current_leads", "open_work", "recent_execution"] },
  period: { type: "string", enum: ["morning", "evening"] },
  scope: { type: "string", enum: ["execution", "outcome"] },
};

const WORKFLOW_OPERATIONS = [
  "status", "current_work", "approvals", "blockers", "latest_artifact",
  "proposed_next_action", "approve", "reject", "request_revision", "continue",
  "resume", "recover", "projection", "sync_notion",
  "additional_research", "deliver_internal_review",
];
const WORKFLOW_DECISION_OPERATIONS = new Set(["approve", "reject", "request_revision"]);
const WORKFLOW_NATIVE_APPROVAL_OPERATIONS = new Set(["sync_notion"]);
const WORKFLOW_REFERENCE_OPTIONAL = new Set(["current_work", "approvals", "blockers", "recover"]);
const WORKFLOW_SCHEMA = {
  operation: { type: "string", enum: WORKFLOW_OPERATIONS },
  reference: { type: "string", minLength: 1, maxLength: 500 },
  rationale: { type: "string", minLength: 1, maxLength: 1000 },
  approval_token: { type: "string", minLength: 64, maxLength: 64 },
  recipient: { type: "string", minLength: 1, maxLength: 320 },
  inputs: { type: "object", additionalProperties: true },
};
const ATTENTION_SCHEMA = {
  operation: { type: "string", enum: ["ignore", "suppress", "mark_test", "archive", "restore", "watch", "show", "list", "archive_safe_tests", "suppress_safe_tests"] },
  reference: { type: "string", minLength: 1, maxLength: 500 },
  reason: { type: "string", maxLength: 1000 },
  scope: { type: "string", enum: ["visible", "suppressed", "test", "archived", "all"] },
};

function commandForStateRead(params) {
  const view = String(params?.view || "").toLowerCase();
  if (view === "executive_brief") {
    const period = String(params?.period || "morning").toLowerCase();
    if (!new Set(["morning", "evening"]).has(period)) throw new Error("period must be morning or evening");
    return `/${period}`;
  }
  if (view === "current_leads") return "/leads";
  if (view === "open_work") return "/mission";
  if (view === "recent_execution") {
    const scope = String(params?.scope || "execution").toLowerCase();
    if (!new Set(["execution", "outcome"]).has(scope)) throw new Error("scope must be execution or outcome");
    return scope === "execution" ? "/did that happen" : "/did that work";
  }
  throw new Error(`unsupported Narratiive state view: ${view || "missing"}`);
}

function controlPlaneUrl() {
  let url = String(process.env.TONY_AGENT_CONTROL_PLANE_URL || process.env.TONY_TELEGRAM_BRIDGE_URL || DEFAULT_URL).replace(/\/$/, "");
  if (url === "http://127.0.0.1:8790" || url === "http://localhost:8790") url += "/control-plane";
  return url;
}

function controlPlaneTimeoutMs() {
  const configured = Number(process.env.TONY_CONTROL_PLANE_TIMEOUT_MS || DEFAULT_CONTROL_PLANE_TIMEOUT_MS);
  return Number.isFinite(configured) && configured > 0 ? configured : DEFAULT_CONTROL_PLANE_TIMEOUT_MS;
}

function workflowControlUrl() {
  return controlPlaneUrl().replace(/\/control-plane$/, "/workflow/control");
}

async function executeWorkflowControl(params) {
  const operation = String(params?.operation || "").toLowerCase();
  if (!WORKFLOW_OPERATIONS.includes(operation)) throw new Error("unsupported workflow operation");
  const reference = String(params?.reference || "").trim();
  const rationale = String(params?.rationale || "").trim();
  if (!WORKFLOW_REFERENCE_OPTIONAL.has(operation) && !reference) throw new Error("workflow reference is required");
  if ((WORKFLOW_DECISION_OPERATIONS.has(operation) || WORKFLOW_NATIVE_APPROVAL_OPERATIONS.has(operation)) && !rationale) throw new Error("workflow decisions require a rationale");
  const approvalToken = String(params?.approval_token || "").trim();
  if (WORKFLOW_DECISION_OPERATIONS.has(operation) && !approvalToken) throw new Error("workflow decision requires the current approval token");
  const token = resolveBridgeToken();
  const headers = { "content-type": "application/json", accept: "application/json" };
  if (token) headers.authorization = `Bearer ${token}`;
  const timeoutMs = controlPlaneTimeoutMs();
  let response;
  try {
    response = await fetch(workflowControlUrl(), {
      method: "POST",
      headers,
      body: JSON.stringify({
        operation,
        reference,
        rationale,
        inputs: {
          ...(params?.inputs && typeof params.inputs === "object" && !Array.isArray(params.inputs) ? params.inputs : {}),
          ...(approvalToken ? { approval_token: approvalToken } : {}),
          ...(params?.recipient ? { recipient: String(params.recipient) } : {}),
        },
        approval_granted: WORKFLOW_NATIVE_APPROVAL_OPERATIONS.has(operation),
        source: "openclaw_telegram_workflow_tool",
      }),
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (error) {
    if (error?.name === "TimeoutError" || error?.name === "AbortError") throw new Error(`Narratiive workflow control timed out after ${timeoutMs}ms`);
    throw error;
  }
  const raw = await response.text();
  let payload;
  try { payload = JSON.parse(raw || "{}"); } catch { throw new Error("Narratiive workflow control returned invalid JSON"); }
  if (!response.ok) throw new Error(`Narratiive workflow control returned HTTP ${response.status}`);
  return payload;
}

async function readControlPlane(params) {
  const token = resolveBridgeToken();
  const headers = { "content-type": "application/json", accept: "application/json" };
  if (token) headers.authorization = `Bearer ${token}`;
  const timeoutMs = controlPlaneTimeoutMs();
  let response;
  try {
    response = await fetch(controlPlaneUrl(), {
      method: "POST",
      headers,
      body: JSON.stringify({ text: commandForStateRead(params), source: "openclaw_native_tool" }),
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (error) {
    if (error?.name === "TimeoutError" || error?.name === "AbortError") {
      throw new Error(`Narratiive control plane timed out after ${timeoutMs}ms`);
    }
    throw error;
  }
  const raw = await response.text();
  let payload;
  try { payload = JSON.parse(raw || "{}"); } catch { throw new Error("Narratiive control plane returned invalid JSON"); }
  if (!response.ok) throw new Error(`Narratiive control plane returned HTTP ${response.status}`);
  return payload;
}

function renderToolResult(payload) {
  return { content: [{ type: "text", text: JSON.stringify(payload) }], details: payload };
}

function stateReadTool() {
  return {
    name: "narratiive_read_state",
    description: "Read one authoritative Narratiive OS state view: executive brief, current leads, open work, or recent execution/outcome evidence. This tool is read-only and never mutates external systems.",
    parameters: schema(STATE_READ_SCHEMA, ["view"]),
    async execute(_id, params) {
      try {
        return renderToolResult(await readControlPlane(params || {}));
      } catch (error) {
        return renderToolResult({ ok: false, error: String(error?.message || error) });
      }
    },
  };
}

function safeReadTool() {
  return {
    name: "narratiive_execute_safe_read",
    description: "Execute one bounded read-only inspection through Narratiive OS without approval. This tool refuses writes or preparation, requires evidence proving no mutation occurred, and returns verified source evidence or a fail-closed result.",
    parameters: schema(SAFE_READ_SCHEMA, ["action", "surface", "kind"]),
    async execute(_id, params) {
      try {
        const proposal = buildActionProposal(params || {});
        if (proposal.proposal.approval_required || proposal.proposal.effective_kind !== "read") {
          return renderToolResult({
            ok: false,
            status: "safe_read_rejected",
            proposal: proposal.proposal,
            execution_truth: "not_dispatched",
          });
        }
        return renderToolResult(await executeSafeRead(params || {}));
      } catch (error) {
        return renderToolResult({ ok: false, error: String(error?.message || error), execution_truth: "not_dispatched" });
      }
    },
  };
}

function approvalTool() {
  return {
    name: "narratiive_request_action_approval",
    description: "Request native single-use approval for one bounded consequential Narratiive action. If Matt allows it once, the same approved tool call dispatches only that exact action through Narratiive OS and returns verified execution evidence or a fail-closed result.",
    parameters: schema(ACTION_SCHEMA, ["action", "surface", "kind"]),
    async execute(_id, params) {
      try {
        const requirement = buildNativeApprovalRequirement(params || {});
        if (!requirement.required) {
          return renderToolResult({
            ok: false,
            status: "approval_not_required",
            proposal: requirement.proposal,
            execution_truth: "not_dispatched",
          });
        }
        return renderToolResult(await executeApprovedAction(params || {}));
      } catch (error) {
        return renderToolResult({ ok: false, error: String(error?.message || error), approval_granted: false, execution_truth: "not_dispatched" });
      }
    },
  };
}

function workflowControlTool() {
  return {
    name: "narratiive_workflow_control",
    description: "Read or control durable Narratiive workflows by run, client, company or lead reference. For a substantial artefact at a human gate, call deliver_internal_review so the full immutable review copy goes only to hello@narratiive.com and Telegram receives a concise summary. Interpret Matt's natural Telegram reply, but call approve, reject or request_revision only when intent is unambiguous and include the exact approval_token returned for the current gate; stale tokens fail closed. Notion projection remains a separate native single-use approval. Continue may supply structured discovery evidence or approved research sources for the next registered workflow.",
    parameters: schema(WORKFLOW_SCHEMA, ["operation"]),
    async execute(_id, params) {
      try {
        return renderToolResult(await executeWorkflowControl(params || {}));
      } catch (error) {
        return renderToolResult({ ok: false, error: String(error?.message || error), execution_truth: "not_verified" });
      }
    },
  };
}

function attentionControlTool() {
  return { name: "narratiive_manage_attention", description: "Manage reversible internal lead attention state. Use for explicit SAFE/test suppression, archive, restore and listing; ambiguous references fail safely. This never contacts anyone or performs an external action.", parameters: schema(ATTENTION_SCHEMA, ["operation"]), async execute(_id, params) {
    try {
      const url = controlPlaneUrl().replace(/\/control-plane$/, "/attention/control"); const token = resolveBridgeToken(); const headers = { "content-type": "application/json" }; if (token) headers.authorization = `Bearer ${token}`;
      const response = await fetch(url, { method: "POST", headers, body: JSON.stringify(params || {}), signal: AbortSignal.timeout(controlPlaneTimeoutMs()) }); const payload = await response.json(); return renderToolResult(payload);
    } catch (error) { return renderToolResult({ ok: false, error: String(error?.message || error), external_action_taken: false }); }
  } };
}

export default definePluginEntry({
  id: "narratiive-control-plane",
  name: "Narratiive Control Plane",
  description: "Authoritative Narratiive OS state and evidence plus bounded autonomous reads, native approval and verified consequence execution for Tony.",
  register(api) {
    api.on("before_tool_call", async (event) => {
      if (event.toolName === "narratiive_request_action_approval") {
        const requirement = buildNativeApprovalRequirement(event.params || {});
        if (!requirement.required) return;
        return { requireApproval: requirement.requireApproval };
      }
      if (event.toolName === "narratiive_workflow_control") {
        const requirement = buildWorkflowApprovalRequirement(event.params || {});
        if (!requirement.required) return;
        return { requireApproval: requirement.requireApproval };
      }
    });

    api.registerTool(stateReadTool());
    api.registerTool(safeReadTool());
    api.registerTool(approvalTool());
    api.registerTool(workflowControlTool());
    api.registerTool(attentionControlTool());
  },
});
