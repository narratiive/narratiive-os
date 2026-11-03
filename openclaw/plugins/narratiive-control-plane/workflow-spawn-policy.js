function payloadFromResult(result) {
  if (result?.details && typeof result.details === "object") return result.details;
  const content = Array.isArray(result?.content) ? result.content : [];
  const text = content.find((item) => item?.type === "text" && typeof item.text === "string")?.text;
  if (!text) return {};
  try {
    const payload = JSON.parse(text);
    return payload && typeof payload === "object" ? payload : {};
  } catch {
    return {};
  }
}

export function hookRunKey(event, context) {
  return String(context?.runId || event?.runId || context?.sessionKey || "").trim();
}

export function failedCommissionEvidence(result, now = Date.now()) {
  const payload = payloadFromResult(result);
  if (payload.ok === true && payload?.data?.commissioned === true) return null;
  return {
    failedAt: now,
    reason: String(payload.message || payload.reply || payload.error || "canonical workflow commission was not verified"),
  };
}

export function retainFailedCommission(existing, result, now = Date.now()) {
  return failedCommissionEvidence(result, now) || existing || null;
}

export function blocksSpecialistSpawn(record) {
  return Boolean(record && Number.isFinite(record.failedAt));
}
