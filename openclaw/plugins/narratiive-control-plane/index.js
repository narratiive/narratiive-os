import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const DEFAULT_URL = "http://127.0.0.1:8790/telegram/inbound";

function schema(properties = {}) {
  return { type: "object", properties, additionalProperties: false };
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

async function readControlPlane(api, name, params) {
  const configured = api?.config?.controlPlaneUrl;
  const url = String(configured || process.env.TONY_AGENT_CONTROL_PLANE_URL || process.env.TONY_TELEGRAM_BRIDGE_URL || DEFAULT_URL).replace(/\/$/, "");
  const token = String(process.env.TONY_BRIDGE_TOKEN || "").trim();
  const headers = { "content-type": "application/json", accept: "application/json" };
  if (token) headers.authorization = `Bearer ${token}`;
  const response = await fetch(url, {
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

function tool(name, description, parameters) {
  return { name, description, parameters, async execute(_id, params, ctx) {
    try {
      const payload = await readControlPlane(ctx?.api, name, params || {});
      return { content: [{ type: "text", text: JSON.stringify(payload) }], details: payload };
    } catch (error) {
      const failure = { ok: false, error: String(error?.message || error) };
      return { content: [{ type: "text", text: JSON.stringify(failure) }], details: failure };
    }
  }};
}

export default definePluginEntry({
  id: "narratiive-control-plane",
  name: "Narratiive Control Plane",
  description: "Read-only authoritative Narratiive OS evidence for Tony.",
  register(api) {
    api.registerTool(tool(
      "narratiive_executive_brief",
      "Read the current evidence-backed Narratiive executive brief before advising what matters or needs attention.",
      schema({ period: { type: "string", enum: ["morning", "evening"] } }),
    ));
    api.registerTool(tool(
      "narratiive_current_leads",
      "Read the authoritative current inbound lead and commercial pipeline view.",
      schema(),
    ));
    api.registerTool(tool(
      "narratiive_open_work_status",
      "Read current pending, delegated, stalled or most-recent Tony work status from Narratiive OS.",
      schema(),
    ));
    api.registerTool(tool(
      "narratiive_recent_execution_status",
      "Read verified evidence that a recent consequential action happened, or separately whether it produced a business outcome.",
      schema({ scope: { type: "string", enum: ["execution", "outcome"] } }),
    ));
  },
});
