import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const PLUGIN_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPOSITORY_ROOT = path.resolve(PLUGIN_DIR, "../../..");
const EXECUTOR = path.join(REPOSITORY_ROOT, "scripts", "execute_tony_safe_read.py");

export function executeSafeRead(params = {}, options = {}) {
  const python = String(options.python || process.env.TONY_PYTHON || "python3");
  const timeoutMs = Number(options.timeoutMs || process.env.TONY_SAFE_READ_TIMEOUT_MS || 30000);
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
        status: "safe_read_timeout",
        error: "Narratiive safe-read executor timed out",
        execution_truth: "dispatch_attempted_unverified",
      });
    }, timeoutMs);

    child.stdout.on("data", (chunk) => { stdout += chunk.toString("utf8"); });
    child.stderr.on("data", (chunk) => { stderr += chunk.toString("utf8"); });
    child.on("error", (error) => finish({
      ok: false,
      status: "safe_read_executor_unavailable",
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
          status: "safe_read_invalid_response",
          error: stderr.trim() || "Narratiive safe-read executor returned invalid JSON",
          execution_truth: "dispatch_attempted_unverified",
        });
        return;
      }
      finish(parsed);
    });

    child.stdin.end(JSON.stringify(payload));
  });
}
