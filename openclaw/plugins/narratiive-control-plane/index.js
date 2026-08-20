import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { buildActionProposal } from "./action-policy.js";

const DEFAULT_URL = "http://127.0.0.1:8790/telegram/inbound";

function schema(properties = {}, required = []) {
  return { type: "object", properties, required, additionalProperties: false };
}

function commandFor(name, params) {
  if (name === "narratiive_executive_brief") {
    const period = String(params?.period || "morning").toLowerCase();
    if (!new Set(["morning", "evening"]).has(period)) throw new Error("period must be morning or evening");
    return `/${period}`;
  }
  if (name === "narratiive_current_leads") return "/leads";
  if (name === "narratiive_open_work_status") return "what's the status";
  if (name === "narratiive_recent_execution_status") {
    const scope = String(params?.scope || "execution").toLowerCase();
    if (!new Set(["execution", "outcome"]).has(scope)) throw new Error("scope must be execution or outcome");
    return scope === "execution" ? "did that happen" : "did that work";
  }
  throw new Error(`unsupported Narratiive tool: ${name}`);
}

function controlPlaneUrl() {
  let url = String(process.env.TONY_AGENT_CONTROL_PLANE_URL || process.env.TONY_TELEGRAM_BRIDGE_URL || DEFAULT_URL).replace(/\/$/, "");
  if (url === "http://127.0.0.1:8790" || url === "http://localhost:8790") url += "/telegram/inbound";
  return url;
}

async function readControlPlane(name, params) {
  const token = String(process.env.TONY_BRIDGE_TOKEN || "").trim();
  const headers = { "content-type": "application/json", accept: "application/json" };
  if (token) headers.authorization = `Bearer ${token}`;
  const response = await fetch(controlPlaneUrl(), {
    method: "POST",
    headers,
    body: JSON.stringify({ text: commandFor(name, params), source: "openclaw_native_tool" }),
  });
  const raw = await response.text();
  let payload;
  try { payload = JSON.parse(raw || "{}"); } catch { throw new Error("Narratiive control plane returned invalid JSON"); }
  if (!response.ok) throw new Error(`Narratiive control plane returned HTTP ${response.status}`);
  return payload;
}

function renderToolResult(payload) {
  return { content: [{ type: "text", text: JSON.stringify(payload) }], details: payload };
}

function remoteTool(name, description, parameters) {
  return {
    name,
    description,
    parameters,
    async execute(_id, params) {
      try {
        return renderToolResult(await readControlPlane(name, params || {}));
      } catch (error) {
        return renderToolResult({ ok: false, error: String(error?.message || error) });
      }
    },
  };
}

function proposalTool() {
  return {
    name: "narratiive_propose_action",
    description: "Convert Tony's interpreted next action into a bounded Narratiive execution proposal. This tool never executes, sends, mutates, or grants approval; it only classifies the consequence boundary and returns what may happen next.",
    parameters: schema({
      action: { type: "string", minLength: 1, maxLength: 4000 },
      surface: { type: "string", enum: ["research", "strategy", "creative", "production", "gmail", "calendar", "notion", "drive", "github", "n8n", "replit", "other"] },
      kind: { type: "string", enum: ["read", "prepare", "write"] },
      target: { type: "object", additionalProperties: true },
    }, ["action", "surface", "kind"]),
    async execute(_id, params) {
      try {
        return renderToolResult(buildActionProposal(params || {}));
      } catch (error) {
        return renderToolResult({ ok: false, error: String(error?.message || error), execution_truth: "not_dispatched" });
      }
    },
  };
}

export default definePluginEntry({
  id: "narratiive-control-plane",
  name: "Narratiive Control Plane",
  description: "Authoritative Narratiive OS evidence plus bounded action-proposal policy for Tony.",
  register(api) {
    api.registerTool(remoteTool(
      "narratiive_executive_brief",
      "Read the current evidence-backed Narratiive executive brief before advising what matters or needs attention.",
      schema({ period: { type: "string", enum: ["morning", "evening"] } }),
    ));
    api.registerTool(remoteTool(
      "narratiive_current_leads",
      "Read the authoritative current inbound lead and commercial pipeline view.",
      schema(),
    ));
    api.registerTool(remoteTool(
      "narratiive_open_work_status",
      "Read current pending, delegated, stalled or most-recent Tony work status from Narratiive OS.",
      schema(),
    ));
    api.registerTool(remoteTool(
      "narratiive_recent_execution_status",
      "Read verified evidence that a recent consequential action happened, or separately whether it produced a business outcome.",
      schema({ scope: { type: "string", enum: ["execution", "outcome"] } }),
    ));
    api.registerTool(proposalTool());
  },
});
