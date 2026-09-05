import { buildActionProposal } from "./action-policy.js";

function compactTarget(target) {
  if (!target || typeof target !== "object" || Array.isArray(target)) return "unspecified target";
  const preferredKeys = ["contact", "company", "email", "event", "record", "file", "url", "id"];
  const parts = [];
  for (const key of preferredKeys) {
    const value = target[key];
    if (value !== undefined && value !== null && String(value).trim()) parts.push(`${key}=${String(value).trim()}`);
    if (parts.length >= 3) break;
  }
  return parts.length ? parts.join(", ") : "specified target";
}

export function buildNativeApprovalRequirement(params = {}) {
  const result = buildActionProposal(params);
  const proposal = result.proposal;
  if (!proposal.approval_required) {
    return { required: false, proposal };
  }

  const title = `Approve ${proposal.surface} action`.slice(0, 80);
  const description = `${proposal.requested_action} | ${compactTarget(proposal.target)} | This may change external or persisted state.`.slice(0, 512);
  const severity = new Set(["github", "n8n", "replit"]).has(proposal.surface) ? "critical" : "warning";

  return {
    required: true,
    proposal,
    requireApproval: {
      title,
      description,
      severity,
      allowedDecisions: ["allow-once", "deny"],
      timeoutMs: 120000,
    },
  };
}

export function approvedActionResult(params = {}) {
  const { proposal } = buildNativeApprovalRequirement(params);
  return {
    ok: true,
    status: proposal.approval_required ? "action_approved_for_dispatch" : "approval_not_required",
    proposal,
    approval_granted: proposal.approval_required,
    approval_scope: proposal.approval_required
      ? {
          action: proposal.requested_action,
          surface: proposal.surface,
          target: proposal.target,
          decision: "allow-once",
          single_use: true,
        }
      : null,
    external_action_taken: false,
    execution_truth: proposal.approval_required ? "approved_not_dispatched" : "not_dispatched",
    next_step: proposal.approval_required
      ? "Dispatch only this approved bounded action through Narratiive OS, then verify returned execution evidence before claiming completion."
      : "No approval gate is required; use an authorised bounded read/preparation tool and verify returned evidence.",
  };
}

export function buildWorkflowApprovalRequirement(params = {}) {
  const operation = String(params.operation || "").toLowerCase();
  if (!new Set(["approve", "reject", "request_revision", "sync_notion"]).has(operation)) {
    return { required: false };
  }
  const reference = String(params.reference || "workflow").slice(0, 160);
  const rationale = String(params.rationale || "").slice(0, 240);
  return {
    required: true,
    requireApproval: {
      title: `Approve workflow ${operation.replaceAll("_", " ")}`.slice(0, 80),
      description: `${reference} | ${rationale} | Single use; persisted and auditable.`.slice(0, 512),
      severity: operation === "sync_notion" ? "warning" : "info",
      allowedDecisions: ["allow-once", "deny"],
      timeoutMs: 120000,
    },
  };
}
