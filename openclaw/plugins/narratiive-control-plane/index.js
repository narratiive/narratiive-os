import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { buildActionProposal } from "./action-policy.js";
import { buildNativeApprovalRequirement } from "./approval-policy.js";
import { executeApprovedAction } from "./execution-client.js";
import { executeSafeRead } from "./safe-read-client.js";

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

function commandForStateRead(params) {
  const view = String(params?.view || "").toLowerCase();
  if (view === "executive_brief") {
    const period = String(params?.period || "morning").toLowerCase();
    if (!new Set(["morning", "evening"]).has(period)) throw new Error("period must be morning or evening");
    return `/${period}`;
  }
  if (view === "current_leads") return "/leads";
  if (view === "open_work") return "/what's the status";
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

async function readControlPlane(params) {
  const token = String(process.env.TONY_BRIDGE_TOKEN || "").trim();
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

export default definePluginEntry({
  id: "narratiive-control-plane",
  name: "Narratiive Control Plane",
  description: "Authoritative Narratiive OS state and evidence plus bounded autonomous reads, native approval and verified consequence execution for Tony.",
  register(api) {
    api.on("before_tool_call", async (event) => {
      if (event.toolName !== "narratiive_request_action_approval") return;
      const requirement = buildNativeApprovalRequirement(event.params || {});
      if (!requirement.required) return;
      return { requireApproval: requirement.requireApproval };
    });

    api.registerTool(stateReadTool());
    api.registerTool(safeReadTool());
    api.registerTool(approvalTool());
  },
});
