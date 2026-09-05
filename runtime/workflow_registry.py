from __future__ import annotations

from collections.abc import Iterable

from runtime.definitions import (
    ApprovalPolicy,
    InputContract,
    OutputContract,
    RetryPolicy,
    StageDefinition,
    WorkflowDefinition,
)


class WorkflowNotFound(KeyError):
    pass


class WorkflowRegistry:
    """Validated, deterministic registry of executable workflow contracts."""

    def __init__(self, definitions: Iterable[WorkflowDefinition] = ()) -> None:
        self._definitions: dict[str, WorkflowDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: WorkflowDefinition) -> None:
        if definition.workflow_id in self._definitions:
            raise ValueError(f"duplicate workflow_id: {definition.workflow_id}")
        _validate_definition(definition)
        self._definitions[definition.workflow_id] = definition

    def resolve(self, workflow_id: str) -> WorkflowDefinition:
        try:
            return self._definitions[workflow_id]
        except KeyError as exc:
            raise WorkflowNotFound(workflow_id) from exc

    def all(self) -> tuple[WorkflowDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))

    def validate(self) -> None:
        for definition in self._definitions.values():
            _validate_definition(definition)
            if definition.next_workflow_id and definition.next_workflow_id not in self._definitions:
                raise ValueError(
                    f"workflow {definition.workflow_id} references unknown next workflow: "
                    f"{definition.next_workflow_id}"
                )


def _step(
    step_id: str,
    *,
    capability: str,
    inputs: tuple[str, ...],
    outputs: tuple[str, ...],
    quality: str,
    approval_required: bool,
    agent_ref: str = "",
    side_effect: str = "preparation",
    max_attempts: int = 2,
) -> StageDefinition:
    return StageDefinition(
        stage_id=step_id,
        agent_ref=agent_ref,
        required_inputs=inputs,
        capability=capability,
        input_contract=InputContract(inputs),
        output_contract=OutputContract(outputs),
        quality_contract=quality,
        retry_policy=RetryPolicy(max_attempts=max_attempts),
        approval_policy=ApprovalPolicy(
            required=approval_required,
            before_external_action=True,
        ),
        side_effect_classification=side_effect,
    )


def _workflow(
    workflow_id: str,
    step: StageDefinition,
    *,
    next_workflow_id: str = "",
    approval_required: bool,
    entity_type: str = "client",
) -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id=workflow_id,
        stages=(step,),
        approval_required=approval_required,
        entity_type=entity_type,
        next_workflow_id=next_workflow_id,
        failure_policy="block_and_escalate",
        autonomous_handoff=False,
    )


GROWTH_DIAGNOSTIC_TO_BLUEPRINT_LITE = _workflow(
    "growth_diagnostic_to_blueprint_lite",
    _step(
        "prepare_blueprint_lite",
        capability="strategic_reasoning",
        agent_ref="Claude",
        inputs=("diagnostic_input_package",),
        outputs=(
            "blueprint_lite",
            "diagnostic_signals_used",
            "diagnostic_input_coverage",
            "source_backed_evidence",
            "evidence_gaps",
            "fact_interpretation_hypothesis_lineage",
            "growth_tension",
            "provisional_opportunity",
            "questions_to_answer_next",
            "quality_gate",
            "recommendation",
        ),
        quality="blueprint_lite_quality_gate",
        approval_required=True,
    ),
    next_workflow_id="blueprint_lite_to_discovery_preparation",
    approval_required=True,
    entity_type="lead",
)

BLUEPRINT_LITE_TO_DISCOVERY_PREPARATION = _workflow(
    "blueprint_lite_to_discovery_preparation",
    _step(
        "prepare_discovery",
        capability="strategic_reasoning",
        inputs=("blueprint_lite", "diagnostic_evidence", "company_context"),
        outputs=(
            "discovery_hypotheses",
            "discovery_questions",
            "knowledge_gaps",
            "strategic_tensions",
            "suggested_meeting_objective",
        ),
        quality="discovery_preparation_quality_gate",
        approval_required=True,
    ),
    next_workflow_id="discovery_evidence_to_growth_sprint_proposal",
    approval_required=True,
)

DISCOVERY_EVIDENCE_TO_GROWTH_SPRINT_PROPOSAL = _workflow(
    "discovery_evidence_to_growth_sprint_proposal",
    _step(
        "prepare_growth_sprint_proposal",
        capability="copy_drafting",
        inputs=("discovery_evidence", "blueprint_lite", "commercial_context"),
        outputs=(
            "discovery_synthesis",
            "proposed_scope",
            "recommended_growth_sprint",
            "commercial_proposal_inputs",
            "draft_client_communication",
        ),
        quality="growth_sprint_proposal_quality_gate",
        approval_required=True,
    ),
    next_workflow_id="growth_sprint_to_research_engine",
    approval_required=True,
)

GROWTH_SPRINT_TO_RESEARCH_ENGINE = _workflow(
    "growth_sprint_to_research_engine",
    _step(
        "orchestrate_research",
        capability="market_research",
        inputs=("approved_growth_sprint_scope", "research_requirements", "client_context"),
        outputs=("research_tasks", "evidence_pack", "source_provenance", "research_gaps"),
        quality="research_evidence_quality_gate",
        approval_required=False,
    ),
    next_workflow_id="research_to_growth_blueprint",
    approval_required=False,
)

RESEARCH_TO_GROWTH_BLUEPRINT = _workflow(
    "research_to_growth_blueprint",
    _step(
        "prepare_growth_blueprint",
        capability="strategic_reasoning",
        inputs=("evidence_pack", "approved_growth_sprint_scope", "client_context"),
        outputs=(
            "market_category_diagnosis",
            "audience",
            "growth_barriers",
            "source_of_difference",
            "positioning",
            "narrative",
            "growth_opportunity",
            "activation_implications",
            "evidence_lineage",
        ),
        quality="growth_blueprint_quality_gate",
        approval_required=True,
    ),
    next_workflow_id="growth_blueprint_to_campaign_world",
    approval_required=True,
)

GROWTH_BLUEPRINT_TO_CAMPAIGN_WORLD = _workflow(
    "growth_blueprint_to_campaign_world",
    _step(
        "generate_campaign_world",
        capability="strategic_reasoning",
        inputs=("approved_growth_blueprint", "evidence_lineage", "activation_implications"),
        outputs=("campaign_world", "strategic_handoff", "evidence_lineage"),
        quality="campaign_world_quality_gate",
        approval_required=True,
    ),
    next_workflow_id="campaign_world_to_creative_bible",
    approval_required=True,
)

CAMPAIGN_WORLD_TO_CREATIVE_BIBLE = _workflow(
    "campaign_world_to_creative_bible",
    _step(
        "prepare_creative_bible",
        capability="copy_drafting",
        inputs=("approved_campaign_world", "growth_blueprint", "production_context"),
        outputs=(
            "message_system",
            "tone",
            "distinctive_assets",
            "creative_principles",
            "formats",
            "production_constraints",
            "creative_directors_bible",
        ),
        quality="creative_bible_quality_gate",
        approval_required=True,
    ),
    next_workflow_id="creative_bible_to_asset_production",
    approval_required=True,
)

CREATIVE_BIBLE_TO_ASSET_PRODUCTION = _workflow(
    "creative_bible_to_asset_production",
    _step(
        "orchestrate_creative_assets",
        capability="creative_asset_production",
        inputs=("approved_creative_bible", "asset_manifest", "production_constraints"),
        outputs=("production_tasks", "asset_versions", "asset_manifest", "production_gaps"),
        quality="creative_asset_production_quality_gate",
        approval_required=True,
    ),
    next_workflow_id="asset_review_to_delivery_preparation",
    approval_required=True,
)

ASSET_REVIEW_TO_DELIVERY_PREPARATION = _workflow(
    "asset_review_to_delivery_preparation",
    _step(
        "prepare_delivery",
        capability="document_generation",
        inputs=("reviewed_assets", "asset_manifest", "delivery_requirements"),
        outputs=("delivery_package", "delivery_manifest", "review_findings", "proposed_delivery_action"),
        quality="delivery_preparation_quality_gate",
        approval_required=True,
    ),
    next_workflow_id="delivery_to_follow_up_next_action",
    approval_required=True,
)

DELIVERY_TO_FOLLOW_UP_NEXT_ACTION = _workflow(
    "delivery_to_follow_up_next_action",
    _step(
        "prepare_follow_up",
        capability="strategic_reasoning",
        inputs=("verified_delivery_evidence", "client_context", "measurement_context"),
        outputs=("recommended_follow_up", "measurement_actions", "draft_client_communication"),
        quality="follow_up_preparation_quality_gate",
        approval_required=True,
    ),
    approval_required=True,
)


NARRATIIVE_PRODUCTION_WORKFLOWS = (
    GROWTH_DIAGNOSTIC_TO_BLUEPRINT_LITE,
    BLUEPRINT_LITE_TO_DISCOVERY_PREPARATION,
    DISCOVERY_EVIDENCE_TO_GROWTH_SPRINT_PROPOSAL,
    GROWTH_SPRINT_TO_RESEARCH_ENGINE,
    RESEARCH_TO_GROWTH_BLUEPRINT,
    GROWTH_BLUEPRINT_TO_CAMPAIGN_WORLD,
    CAMPAIGN_WORLD_TO_CREATIVE_BIBLE,
    CREATIVE_BIBLE_TO_ASSET_PRODUCTION,
    ASSET_REVIEW_TO_DELIVERY_PREPARATION,
    DELIVERY_TO_FOLLOW_UP_NEXT_ACTION,
)


def build_narratiive_workflow_registry() -> WorkflowRegistry:
    registry = WorkflowRegistry(NARRATIIVE_PRODUCTION_WORKFLOWS)
    registry.validate()
    return registry


def _validate_definition(definition: WorkflowDefinition) -> None:
    for step in definition.stages:
        if not step.capability:
            raise ValueError(f"workflow {definition.workflow_id} step {step.stage_id} has no capability")
        if not step.input_contract.required_fields or not step.output_contract.required_fields:
            raise ValueError(f"workflow {definition.workflow_id} step {step.stage_id} has an incomplete contract")
        if not step.quality_contract:
            raise ValueError(f"workflow {definition.workflow_id} step {step.stage_id} has no quality contract")
        if step.side_effect_classification == "external_write" and not step.approval_policy.required:
            raise ValueError("external-write workflow steps require approval")
