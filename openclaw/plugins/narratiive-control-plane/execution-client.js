import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const PLUGIN_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPOSITORY_ROOT = path.resolve(PLUGIN_DIR, "../../..");
const EXECUTOR = path.join(REPOSITORY_ROOT, "scripts", "execute_tony_structured_action.py");

export function executeApprovedAction(params = {}, options = {}) {
  const python = String(options.python || process.env.TONY_PYTHON || "python3");
  const timeoutMs = Number(options.timeoutMs || process.env.TONY_APPROVED_ACTION_TIMEOUT_MS || 30000);
  const payload = {
    action: params.action,
    surface: params.surface,
    kind: params.kind,
    target: params.target && typeof params.target === "object" && !Array.isArray(params.target) ? params.target : {},
  };

  return new Promise((resolve) => {
    const child = spawn(python, [EXECUTOR], {
      cwd: REPOSITORY_ROOT,
      env: process.env,
      stdio: ["pipe", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    let settled = false;

    const finish = (result) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(result);
    };

    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      finish({
        ok: false,
        status: "approved_action_timeout",
        error: "Narratiive approved action executor timed out",
        execution_truth: "not_verified",
      });
    }, timeoutMs);

    child.stdout.on("data", (chunk) => { stdout += chunk.toString("utf8"); });
    child.stderr.on("data", (chunk) => { stderr += chunk.toString("utf8"); });
    child.on("error", (error) => finish({
      ok: false,
      status: "approved_action_executor_unavailable",
      error: String(error?.message || error),
      execution_truth: "not_dispatched",
    }));
    child.on("close", () => {
      let parsed;
      try {
        parsed = JSON.parse(stdout.trim() || "{}");
      } catch {
        finish({
          ok: false,
          status: "approved_action_invalid_response",
          error: stderr.trim() || "Narratiive approved action executor returned invalid JSON",
          execution_truth: "not_verified",
        });
        return;
      }
      finish(parsed);
    });

    child.stdin.end(JSON.stringify(payload));
  });
}
