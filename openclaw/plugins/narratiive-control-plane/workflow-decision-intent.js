import { createHmac } from "node:crypto";

const DECISION_OPERATIONS = new Set(["approve", "reject", "request_revision"]);
const CLASSIFICATION_OPERATION = "classify_synthetic_test";
const TARGET_PATTERN = /\b(?:artefact|artifact|blueprint(?:\s+lite)?|strategy\s+thesis|research\s+report|campaign\s+world|creative(?:\s+director(?:'s|’s))?\s+bible|proposal|version|current\s+work)\b/i;
const NEGATED_INTENT_PATTERN = /\b(?:do\s+not|don't|dont|not|never)\s+(?:explicitly\s+)?(?:approve|reject|revise)\b/i;
const QUESTION_PATTERN = /^\s*(?:can|could|should|would|may)\s+(?:i|we)\b/i;

function normalizedOperation(operation) {
  return String(operation || "").trim().toLowerCase().replaceAll("-", "_");
}

export function hasExplicitWorkflowDecisionIntent(operation, instruction) {
  const decision = normalizedOperation(operation);
  const text = String(instruction || "");
  if (!DECISION_OPERATIONS.has(decision) || !text.trim() || !TARGET_PATTERN.test(text)) return false;
  if (NEGATED_INTENT_PATTERN.test(text) || QUESTION_PATTERN.test(text)) return false;
  if (decision === "approve") {
    return /(?:^|[.!?]\s*|\b(?:i|we)\s+)(?:explicitly\s+)?approve\b/i.test(text);
  }
  if (decision === "reject") {
    return /(?:^|[.!?]\s*|\b(?:i|we)\s+)(?:explicitly\s+)?reject\b/i.test(text);
  }
  return /(?:^|[.!?]\s*)(?:please\s+)?revise\b|\b(?:i|we)\s+(?:explicitly\s+)?(?:request|require)\s+(?:a\s+)?revision\b/i.test(text);
}

export function workflowDecisionProofMaterial({ runId, operation, reference, approvalToken, instruction, authorisationReference = "", classificationScope = {} }) {
  const normalized = normalizedOperation(operation);
  const fields = [
    "narratiive-workflow-decision-v1",
    String(runId || ""),
    normalized,
    String(reference || ""),
    String(approvalToken || ""),
    String(instruction || ""),
  ];
  if (normalized === CLASSIFICATION_OPERATION) {
    fields.push(String(authorisationReference || ""));
    for (const field of ["workspace_id", "client_id", "workflow_id", "run_id"]) fields.push(String(classificationScope?.[field] || ""));
  }
  return fields.join("\0");
}

export function signWorkflowDecisionProof(secret, fields) {
  const key = String(secret || "");
  if (!key) throw new Error("workflow decision proof requires the configured bridge token");
  return createHmac("sha256", key).update(workflowDecisionProofMaterial(fields), "utf8").digest("hex");
}

export function buildTrustedWorkflowDecisionParams(params, trustedTurn, bridgeToken) {
  const operation = normalizedOperation(params?.operation);
  if (!DECISION_OPERATIONS.has(operation)) return params;
  if (!trustedTurn?.runId || typeof trustedTurn.prompt !== "string") {
    throw new Error("workflow artefact decision requires the current trusted human turn");
  }
  const instruction = String(params?.approval_instruction || "");
  if (!instruction || instruction !== trustedTurn.prompt) {
    throw new Error("approval_instruction must exactly equal the verbatim current human instruction");
  }
  if (!hasExplicitWorkflowDecisionIntent(operation, instruction)) {
    throw new Error("the current human instruction must explicitly approve, reject, or request revision of the workflow artefact");
  }
  const approvalToken = String(params?.approval_token || "").trim();
  if (!approvalToken) throw new Error("workflow decision requires the current approval token");
  const fields = {
    runId: trustedTurn.runId,
    operation,
    reference: String(params?.reference || "").trim(),
    approvalToken,
    instruction,
  };
  return {
    ...params,
    approval_instruction: instruction,
    _approval_instruction_run_id: trustedTurn.runId,
    _approval_instruction_proof: signWorkflowDecisionProof(bridgeToken, fields),
  };
}

export function buildTrustedWorkflowClassificationParams(params, trustedTurn, bridgeToken) {
  const operation = normalizedOperation(params?.operation);
  if (operation !== CLASSIFICATION_OPERATION) return params;
  if (!trustedTurn?.runId || typeof trustedTurn.prompt !== "string") {
    throw new Error("workflow classification requires the current trusted human turn");
  }
  const instruction = String(params?.classification_instruction || "");
  if (!instruction || instruction !== trustedTurn.prompt) {
    throw new Error("classification_instruction must exactly equal the verbatim current human instruction");
  }
  if (!/\bclassif(?:y|ication)\b/i.test(instruction) || !/\bsynthetic\b/i.test(instruction)) {
    throw new Error("the current human instruction must explicitly classify this workflow as synthetic");
  }
  const reference = String(params?.reference || "").trim();
  const authorisationReference = String(params?.authorisation_reference || "").trim();
  const suppliedScope = params?.classification_scope;
  const classificationScope = Object.fromEntries(
    ["workspace_id", "client_id", "workflow_id", "run_id"].map((field) => [field, String(suppliedScope?.[field] || "").trim()]),
  );
  if (!reference || !authorisationReference || Object.values(classificationScope).some((value) => !value)) {
    throw new Error("workflow classification requires an exact entity, workspace, client, workflow, run and authorisation reference");
  }
  if (!instruction.includes(reference)) {
    throw new Error("the current human instruction must name the exact workflow entity reference");
  }
  const fields = {
    runId: trustedTurn.runId,
    operation,
    reference,
    approvalToken: "",
    instruction,
    authorisationReference,
    classificationScope,
  };
  return {
    ...params,
    classification_instruction: instruction,
    _classification_instruction_run_id: trustedTurn.runId,
    _classification_instruction_proof: signWorkflowDecisionProof(bridgeToken, fields),
    classification_scope: classificationScope,
  };
}
