import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import os from "node:os";
import path from "node:path";

const PLUGIN_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPOSITORY_ROOT = path.resolve(PLUGIN_DIR, "../../..");
const EXECUTOR_MODULE = "scripts.execute_tony_safe_read";
const ENV_LOADER = path.join(REPOSITORY_ROOT, "scripts", "run_with_env.py");
const REPOSITORY_PYTHON = path.join(REPOSITORY_ROOT, ".venv", "bin", "python");

export function executeSafeRead(params = {}, options = {}) {
  const python = String(options.python || process.env.TONY_PYTHON || REPOSITORY_PYTHON);
  const envFile = String(
    options.envFile
      || process.env.NARRATIIVE_RUNTIME_ENV_FILE
      || path.join(os.homedir(), ".config", "narratiive", "runtime.env"),
  );
  const timeoutMs = Number(options.timeoutMs || process.env.TONY_SAFE_READ_TIMEOUT_MS || 30000);
  const payload = {
    action: params.action,
    surface: params.surface,
    kind: params.kind,
    operation: params.operation,
    target: params.target && typeof params.target === "object" && !Array.isArray(params.target) ? params.target : {},
  };

  return new Promise((resolve) => {
    const child = spawn(python, [ENV_LOADER, envFile, python, "-m", EXECUTOR_MODULE], {
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
    child.on("close", (code) => {
      const output = stdout.trim();
      if (!output) {
        finish({
          ok: false,
          status: "safe_read_executor_failed",
          error: code
            ? `Narratiive safe-read executor exited with code ${code}`
            : "Narratiive safe-read executor returned no result",
          execution_truth: "dispatch_attempted_unverified",
        });
        return;
      }
      let parsed;
      try {
        parsed = JSON.parse(output);
      } catch {
        finish({
          ok: false,
          status: "safe_read_invalid_response",
          error: stderr.trim() || "Narratiive safe-read executor returned invalid JSON",
          execution_truth: "dispatch_attempted_unverified",
        });
        return;
      }
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed) || Object.keys(parsed).length === 0) {
        finish({
          ok: false,
          status: "safe_read_invalid_response",
          error: "Narratiive safe-read executor returned an empty result",
          execution_truth: "dispatch_attempted_unverified",
        });
        return;
      }
      finish(parsed);
    });

    child.stdin.end(JSON.stringify(payload));
  });
}
