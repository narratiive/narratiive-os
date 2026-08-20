const WRITE_MARKERS = [
  "send", "reply to", "follow up with", "follow-up with", "book ", "schedule ",
  "reschedule", "cancel", "invite", "update", "change", "create", "delete",
  "remove", "publish", "deploy", "merge", "commit", "push", "edit", "fix",
  "repair", "implement", "build", "write to", "add to", "share", "email ",
];

const SAFE_READ_SURFACES = new Set(["gmail", "calendar", "notion", "drive", "github", "n8n", "replit"]);
const INTERNAL_PREP_SURFACES = new Set(["research", "strategy", "creative", "production", "other"]);

function normalise(value) {
  return String(value || "").trim();
}

function containsWriteIntent(action) {
  const lowered = normalise(action).toLowerCase();
  return WRITE_MARKERS.some((marker) => lowered.includes(marker));
}

export function buildActionProposal(params = {}) {
  const action = normalise(params.action);
  if (!action) throw new Error("action is required");
  if (action.length > 4000) throw new Error("action is too long");

  const surface = normalise(params.surface || "other").toLowerCase();
  const requestedKind = normalise(params.kind || "prepare").toLowerCase();
  const target = params.target && typeof params.target === "object" && !Array.isArray(params.target) ? params.target : {};

  if (!new Set(["read", "prepare", "write"]).has(requestedKind)) {
    throw new Error("kind must be read, prepare or write");
  }

  // The model's classification is advisory only. Obvious mutation language always
  // wins so conversational interpretation can never silently downgrade a write.
  const effectiveKind = containsWriteIntent(action) ? "write" : requestedKind;
  let approvalRequired = true;
  let executionMode = "approval_gated_write";
  let approvalReason = "the action could change external or persisted state";

  if (effectiveKind === "read" && SAFE_READ_SURFACES.has(surface)) {
    approvalRequired = false;
    executionMode = "autonomous_read";
    approvalReason = "verified read-only inspection is reversible and does not mutate external state";
  } else if (effectiveKind === "prepare" && INTERNAL_PREP_SURFACES.has(surface)) {
    approvalRequired = false;
    executionMode = "autonomous_prepare";
    approvalReason = "internal preparation is reversible and remains subject to Tony review";
  } else if (effectiveKind === "prepare" && SAFE_READ_SURFACES.has(surface)) {
    approvalRequired = false;
    executionMode = "autonomous_prepare";
    approvalReason = "drafting or preparation may proceed internally provided the external system is not mutated";
  }

  const state = approvalRequired ? "awaiting_approval" : "ready_for_autonomous_dispatch";
  return {
    ok: true,
    status: "proposal_prepared",
    proposal: {
      requested_action: action,
      surface,
      requested_kind: requestedKind,
      effective_kind: effectiveKind,
      target,
      approval_required: approvalRequired,
      approval_reason: approvalReason,
      execution_mode: executionMode,
      dispatch: {
        eligible: !approvalRequired,
        state,
        surface,
        instruction: action,
        target,
        execution_mode: executionMode,
        expected_evidence: executionMode === "autonomous_read"
          ? "verified read result with source identifiers and no persisted mutation"
          : executionMode === "autonomous_prepare"
            ? "returned internal work product ready for Tony review"
            : "explicit scoped approval followed by verified execution evidence",
        execution_truth: "not_dispatched",
        return_to: "Tony",
      },
    },
    next_step: approvalRequired
      ? "Ask Matt for explicit scoped approval before any dispatch or external mutation."
      : "Tony may proceed only through an authorised bounded tool or specialist and must verify returned evidence before claiming completion.",
    external_action_taken: false,
    approval_granted: false,
    execution_truth: "proposal_only_not_dispatched",
  };
}
