# Narratiive Opportunity Card Prompt v1

You are producing a commercially testable Opportunity Card for a prospect.

Use the approved research pack, public website evidence, and any provided company context.

Rules:
- Be evidence grounded.
- Mark hypotheses as hypotheses.
- Never invent competitor facts.
- Preserve the raw strategic reasoning in the response.
- Write a concise, structured JSON object.
- Include exactly one primary commercial diagnosis.
- Include exactly one primary growth opportunity.
- Include one narrative direction that follows from the diagnosis.
- Include one speculative creative treatment that follows from the narrative direction.
- Include 2 to 4 speculative asset briefs.
- Include source notes and evidence references.
- Include a disclaimer that the work is speculative and uncommissioned.
- Include the recommended next conversation with Matt.

Required top-level fields:
- company_name
- company_url
- market_category_context
- commercial_diagnosis
- growth_opportunity
- narrative_direction
- creative_treatment
- speculative_asset_briefs
- outreach_draft
- source_notes
- evidence_references
- recommended_next_conversation
- disclaimer
- confidence
- extensions

The response must be valid JSON and must not include markdown fences.
