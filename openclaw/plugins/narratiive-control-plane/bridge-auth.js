import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const TOKEN_KEY = "TONY_BRIDGE_TOKEN";

export function parseRuntimeEnvValue(contents, key = TOKEN_KEY) {
  for (const rawLine of String(contents || "").split(/\r?\n/)) {
    let line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    if (line.startsWith("export ")) line = line.slice(7).trim();
    const separator = line.indexOf("=");
    if (separator < 1 || line.slice(0, separator).trim() !== key) continue;
    const rawValue = line.slice(separator + 1).trim();
    if (
      rawValue.length >= 2
      && ((rawValue.startsWith("'") && rawValue.endsWith("'"))
        || (rawValue.startsWith('"') && rawValue.endsWith('"')))
    ) {
      return rawValue.slice(1, -1);
    }
    return rawValue;
  }
  return "";
}

export function resolveBridgeToken({ env = process.env, readFile = fs.readFileSync, homeDir = os.homedir() } = {}) {
  const inherited = String(env?.[TOKEN_KEY] || "").trim();
  if (inherited) return inherited;
  let envFile = String(env?.NARRATIIVE_ENV_FILE || path.join(homeDir, ".config", "narratiive", "runtime.env"));
  if (envFile.startsWith("~/")) envFile = path.join(homeDir, envFile.slice(2));
  try {
    return parseRuntimeEnvValue(readFile(envFile, "utf8"), TOKEN_KEY).trim();
  } catch {
    return "";
  }
}
