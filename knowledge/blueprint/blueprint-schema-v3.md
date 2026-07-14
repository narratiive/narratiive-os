V3.1 UPDATE (RAVE REVIEW LEARNINGS)


Slide 27 Revision:
- The 'So What' must always describe the business implication of the creative direction, never the commercial value of the Blueprint itself.
- Prohibited: references to selling the next phase, buying the build, purchasing creative development, founder wanting to proceed, or commentary about the document.
- Required structure: Creative Territory → Business Outcome → Strategic Role.
- Example So What: 'These territories translate the position into distinct creative worlds that build memory, trust and conversion while reinforcing the brand’s strategic stance.'


Slide 28 Revision:
- Rename conceptual purpose from '90-Day Plan' to 'Growth Priorities and Dependencies'.
- Recommendations may extend beyond media, marketing or communications.
- Blueprint authors are diagnosing growth constraints, not volunteering to execute operational change.
- Explicitly separate:
  1. Marketing-controlled actions.
  2. Cross-functional dependencies.
  3. Business-level constraints.
- Include a statement explaining that some recommendations sit outside marketing but directly influence retention, LTV and media effectiveness.


Slide 29 Revision:
- Remove prioritisation logic from this slide.
- Prioritisation belongs exclusively on Slide 28.
- Slide 29 becomes a pure Measurement and Learning Framework.
- Required sections:
  • Leading Indicators
  • Performance Indicators
  • Brand Indicators
  • Review Cadence
  • Decision Rules
- The purpose is measurement clarity, not investment prioritisation.


Audience Upgrade Rule:
- Demand pools must feel discovered rather than categorised.
- Prefer behavioural definitions ('Supermarket-Plus Switcher', 'Weekend Ritualist', 'Subscription Sceptic') over consultant labels.
- Every audience segment should be supported by observable evidence, customer language or behavioural signals.


Target quality threshold for future Blueprint generations: 9.5/10 founder-grade output.
# NARRATIIVE BLUEPRINT SCHEMA v3


Status: Active · Version: 3.0 · Owner: Narratiive · Updated for Founder-Grade 30-slide Growth Blueprint


PURPOSE
Codifies the fixed architecture of the Narratiive Growth Blueprint as structured data. The architecture stays stable. Client-specific thinking fills the architecture. Every slide is defined by strategic purpose, visual structure, content requirements, required inputs, outputs and the so_what_test that determines whether the slide earns its place.


Source of truth: 02 Growth Blueprint System + Narratiive Growth Blueprint 30-slide structure + Blueprint Population System + Master Context + Founder Brief + Scoring System + Founder-Grade Upgrade Rules.


CANONICAL STRUCTURE
30 slides across 6 acts:
1-5 Act 1 — The Case for Change
6-10 Act 2 — Market and Competitive Diagnosis
11-15 Act 3 — Audience and Demand Opportunity
16-22 Act 4 — Positioning and Narrative Answer
23-27 Act 5 — The Growth System
28-30 Act 6 — Implementation and Measurement


V3 UPGRADE PRINCIPLES
1. The Blueprint must feel like a founder document, not an agency strategy deck.
2. Every major claim must be supported by evidence, customer language or commercial logic.
3. The deck must contain the five founder-grade upgrades: Customer Evidence, Commercial Prize, Constraint Prioritisation, Creative Direction and Economic Prioritisation.
4. Creative Direction is a hook, not a giveaway. Describe the future campaign world; do not fully execute campaign concepts, mock-ups, art direction or production-ready assets inside the Blueprint.
5. The Blueprint should diagnose, reframe and prioritise. Paid follow-on work should include creative treatment, prototyping, campaign platform development and production planning.
6. Keep the master Blueprint to exactly 30 slides.


NOTE ON DERIVATIVES
The 30-slide version is the full paid master Blueprint. The 5-slide Executive Summary and 10-slide Diagnostic Teaser should be generated from this schema, not treated as separate products.


SCHEMA NOTATION
Each slide is described as a structured object with: slide_no, slide_name, act, purpose, visual_type, layout_type, content_requirements, inputs, outputs, so_what_test.


LAYOUT TYPES
A = text + image / evidence visual
B = full-width statement / premium editorial page
C = two-column framework
D = card grid / evidence board
E = accent framework / system visual
F = commercial model / prioritisation table


================ THE SCHEMA ================


SLIDE 01 — COVER
{
 "slide_no": 1,
 "slide_name": "Cover",
 "act": "Title",
 "purpose": "Frame the document as a premium strategic product, not a presentation. Establish client name, Narratiive authorship and the promise of strategic clarity for scalable growth.",
 "visual_type": "title_lockup",
 "layout_type": "B",
 "content_requirements": ["Client name", "Year", "Document title: THE NARRATIIVE GROWTH BLUEPRINT", "Tagline: STRATEGIC CLARITY FOR SCALABLE GROWTH", "Narratiive wordmark", "www.narratiive.com"],
 "inputs": ["client_name", "delivery_year", "accent_colour"],
 "outputs": ["document_frame"],
 "so_what_test": "Does this feel like a premium strategic product on first glance?"
}


SLIDE 02 — EXECUTIVE THESIS
{
 "slide_no": 2,
 "slide_name": "Executive Thesis",
 "act": "Act 1 — The Case for Change",
 "purpose": "Summarise the central growth argument in one clear strategic thesis. Give the reader the answer before the evidence.",
 "visual_type": "single_thesis_page",
 "layout_type": "B",
 "content_requirements": ["One-line growth thesis", "Three proof points", "One commercial implication", "What must change now"],
 "inputs": ["market_diagnosis", "brand_diagnosis", "growth_constraint", "recommended_direction"],
 "outputs": ["executive_thesis", "strategic_argument"],
 "so_what_test": "Can the founder repeat the argument after one read?"
}


SLIDE 03 — THE COMMERCIAL QUESTION
{
 "slide_no": 3,
 "slide_name": "The Commercial Question",
 "act": "Act 1 — The Case for Change",
 "purpose": "Translate the brief into the commercial question the Blueprint is designed to answer.",
 "visual_type": "question_frame",
 "layout_type": "A",
 "content_requirements": ["Wrong question", "Right question", "Current business ambition", "Definition of growth success", "Scope of the Blueprint"],
 "inputs": ["client_brief", "business_objectives", "commercial_targets", "time_horizon"],
 "outputs": ["commercial_question", "success_definition"],
 "so_what_test": "Does this move the work from marketing activity to business impact?"
}


SLIDE 04 — MARKET REALITY
{
 "slide_no": 4,
 "slide_name": "Market Reality",
 "act": "Act 1 — The Case for Change",
 "purpose": "Explain what is changing in the category, culture, consumer behaviour, media and technology.",
 "visual_type": "ecosystem_map_of_forces",
 "layout_type": "A",
 "content_requirements": ["3-5 structural shifts", "Each shift interpreted, not just stated", "Why the shift matters to this brand", "Evidence points", "Founder insight"],
 "inputs": ["category_shifts", "consumer_shifts", "technology_shifts", "media_shifts", "cultural_shifts"],
 "outputs": ["market_reality_summary", "forces_at_play"],
 "so_what_test": "What has changed that creates an opening for this brand specifically?"
}


SLIDE 05 — CATEGORY GROWTH DYNAMICS
{
 "slide_no": 5,
 "slide_name": "Category Growth Dynamics",
 "act": "Act 1 — The Case for Change",
 "purpose": "Diagnose how growth works in the category: maturity, demand, adoption, pricing, barriers and buyer behaviour.",
 "visual_type": "category_dynamics_map",
 "layout_type": "C",
 "content_requirements": ["Category maturity", "Demand drivers", "Adoption barriers", "Pricing dynamics", "Buyer behaviour patterns", "Where the battle is won"],
 "inputs": ["market_size", "growth_rate", "category_maturity", "purchase_frequency", "price_sensitivity", "barriers_to_adoption"],
 "outputs": ["category_growth_dynamics", "market_battlefield"],
 "so_what_test": "Do we know whether the brand is fighting demand, distinction, distribution, trust or price?"
}


SLIDE 06 — COMPETITIVE LANDSCAPE
{
 "slide_no": 6,
 "slide_name": "Competitive Landscape",
 "act": "Act 2 — Market and Competitive Diagnosis",
 "purpose": "Map the competitive field and show how brands are currently competing.",
 "visual_type": "competitor_landscape",
 "layout_type": "C",
 "content_requirements": ["Key competitors", "Positioning claims", "Channel behaviour", "Strengths and weaknesses", "Dominant category conventions"],
 "inputs": ["competitor_list", "competitor_claims", "competitor_channels", "competitor_strengths", "competitor_weaknesses"],
 "outputs": ["competitive_landscape", "category_conventions"],
 "so_what_test": "Does this show what the market rewards, repeats and ignores?"
}


SLIDE 07 — THE SEA OF SAMENESS
{
 "slide_no": 7,
 "slide_name": "The Sea of Sameness",
 "act": "Act 2 — Market and Competitive Diagnosis",
 "purpose": "Make category sameness visible through language, claims, visual codes and channel behaviours.",
 "visual_type": "sameness_audit",
 "layout_type": "D",
 "content_requirements": ["Competitor screenshots or examples", "Repeated phrases", "Repeated design codes", "Repeated promises", "The consequence of sameness", "Founder insight"],
 "inputs": ["competitor_assets", "website_language", "ad_claims", "visual_codes", "social_content"],
 "outputs": ["sameness_patterns", "distinctiveness_problem"],
 "so_what_test": "Would the client feel uncomfortable seeing how interchangeable the category has become?"
}


SLIDE 08 — THE MARKET GAP
{
 "slide_no": 8,
 "slide_name": "The Market Gap",
 "act": "Act 2 — Market and Competitive Diagnosis",
 "purpose": "Identify the unoccupied or under-leveraged market space created by the category conventions.",
 "visual_type": "white_space_map",
 "layout_type": "E",
 "content_requirements": ["Named market gap", "Why it exists", "Who it matters to", "Why competitors have missed it", "Commercial upside", "Evidence caveat where required"],
 "inputs": ["competitive_landscape", "audience_tensions", "category_conventions", "unmet_needs"],
 "outputs": ["market_gap", "white_space_definition"],
 "so_what_test": "Is this a genuine market gap, not just a nicer way to describe the brand?"
}


SLIDE 09 — GROWTH CONSTRAINT DIAGNOSIS
{
 "slide_no": 9,
 "slide_name": "Growth Constraint Diagnosis",
 "act": "Act 2 — Market and Competitive Diagnosis",
 "purpose": "Name the real constraint holding growth back: awareness, salience, trust, conversion, relevance, distribution, pricing or consistency.",
 "visual_type": "growth_constraint_framework",
 "layout_type": "C",
 "content_requirements": ["Primary growth constraint", "Secondary constraints", "Symptoms vs root causes", "Evidence for the diagnosis", "Commercial implication"],
 "inputs": ["performance_data", "brand_data", "audience_research", "competitive_findings", "client_interviews"],
 "outputs": ["growth_constraint", "root_cause_diagnosis"],
 "so_what_test": "Have we stopped the client solving the wrong problem?"
}


SLIDE 10 — THE PROVOCATION
{
 "slide_no": 10,
 "slide_name": "The Provocation",
 "act": "Act 2 — Market and Competitive Diagnosis",
 "purpose": "State the uncomfortable strategic truth the brand must confront.",
 "visual_type": "provocation_page",
 "layout_type": "B",
 "content_requirements": ["One sharp provocation", "Supporting evidence", "What the brand must stop believing", "What must change", "Commercial consequence of inaction"],
 "inputs": ["growth_constraint", "sameness_patterns", "market_gap", "client_assumptions"],
 "outputs": ["strategic_provocation", "belief_to_change"],
 "so_what_test": "Does this create the 'oh, that is us' moment?"
}


SLIDE 11 — AUDIENCE REALITY
{
 "slide_no": 11,
 "slide_name": "Audience Reality",
 "act": "Act 3 — Audience and Demand Opportunity",
 "purpose": "Show who the brand currently talks to versus who could actually drive growth.",
 "visual_type": "audience_reality_split",
 "layout_type": "C",
 "content_requirements": ["Current audience assumption", "Actual growth audience", "Behavioural evidence", "Motivational evidence", "Implication for targeting"],
 "inputs": ["current_audience", "buyer_data", "research_signals", "social_listening", "search_behaviour"],
 "outputs": ["audience_reality", "growth_audience_hypothesis"],
 "so_what_test": "Does this move beyond lazy demographics?"
}


SLIDE 12 — AUDIENCE SEGMENTS / DEMAND POOLS
{
 "slide_no": 12,
 "slide_name": "Audience Segments / Demand Pools",
 "act": "Act 3 — Audience and Demand Opportunity",
 "purpose": "Define 3-4 growth audiences based on behaviour, motivation, barriers and commercial potential.",
 "visual_type": "demand_pool_cards",
 "layout_type": "D",
 "content_requirements": ["Named demand pools", "Real-world audience evidence", "Motivation", "Barrier", "Commercial value", "Best message or trigger"],
 "inputs": ["segments", "behaviours", "motivations", "barriers", "market_value", "reviews", "social_listening", "search_data"],
 "outputs": ["growth_segments", "demand_pools"],
 "so_what_test": "Are these useful growth pools rather than persona fiction?"
}


SLIDE 13 — CUSTOMER EVIDENCE BOARD
{
 "slide_no": 13,
 "slide_name": "Customer Evidence Board",
 "act": "Act 3 — Audience and Demand Opportunity",
 "purpose": "Ground the strategic diagnosis in real customer language, objections, motivations and signals from reviews, forums, search, social and interviews.",
 "visual_type": "evidence_board",
 "layout_type": "D",
 "content_requirements": ["Customer says", "Search shows", "Reviews reveal", "Social/forums reveal", "Strategic interpretation", "Implication for messaging"],
 "inputs": ["reviews", "reddit_threads", "social_comments", "search_queries", "interview_notes", "sales_objections"],
 "outputs": ["customer_language", "proof_of_need", "evidence_backed_tensions"],
 "so_what_test": "Would a sceptical founder believe the insight exists outside the deck?"
}


SLIDE 14 — AUDIENCE TENSIONS / DECISION CONTEXT
{
 "slide_no": 14,
 "slide_name": "Audience Tensions / Decision Context",
 "act": "Act 3 — Audience and Demand Opportunity",
 "purpose": "Identify what people want, fear, misunderstand or struggle with, and where confidence is built or lost during the decision journey.",
 "visual_type": "tension_plus_journey_matrix",
 "layout_type": "C",
 "content_requirements": ["Consumer desire", "Consumer anxiety", "Category failure", "Discovery/research/compare/hesitate/convert", "Confidence barriers", "Conversion triggers"],
 "inputs": ["reviews", "search_behaviour", "channel_behaviour", "purchase_barriers", "interview_notes"],
 "outputs": ["audience_tensions", "decision_context", "journey_friction"],
 "so_what_test": "Where does consumer hesitation meet category convention, and where must the brand intervene?"
}


SLIDE 15 — CATEGORY ENTRY POINTS
{
 "slide_no": 15,
 "slide_name": "Category Entry Points",
 "act": "Act 3 — Audience and Demand Opportunity",
 "purpose": "Define the situations, triggers, needs and moments where the brand must come to mind.",
 "visual_type": "category_entry_point_map",
 "layout_type": "D",
 "content_requirements": ["Entry points", "Trigger moments", "Need states", "Memory cues", "Messaging implication"],
 "inputs": ["customer_occasions", "need_states", "search_intent", "seasonality", "purchase_triggers"],
 "outputs": ["category_entry_points", "memory_triggers"],
 "so_what_test": "When should this brand be remembered?"
}


SLIDE 16 — CURRENT BRAND DIAGNOSIS
{
 "slide_no": 16,
 "slide_name": "Current Brand Diagnosis",
 "act": "Act 4 — Positioning and Narrative Answer",
 "purpose": "Assess what the brand currently stands for, where it is strong and where it is strategically vague.",
 "visual_type": "brand_diagnosis_scorecard",
 "layout_type": "C",
 "content_requirements": ["Current promise", "Perceived strengths", "Strategic weaknesses", "Distinctive assets present", "Clarity gaps"],
 "inputs": ["website", "social_channels", "ads", "brand_assets", "client_materials"],
 "outputs": ["current_brand_diagnosis", "clarity_gaps"],
 "so_what_test": "Is this candid enough to be useful?"
}


SLIDE 17 — POSITIONING PROBLEM
{
 "slide_no": 17,
 "slide_name": "Positioning Problem",
 "act": "Act 4 — Positioning and Narrative Answer",
 "purpose": "Explain why the current positioning is underpowered, too broad, too generic or not commercially useful.",
 "visual_type": "positioning_problem_framework",
 "layout_type": "C",
 "content_requirements": ["Current position", "Problem with current position", "What it fails to signal", "What it fails to own", "Required shift"],
 "inputs": ["current_brand_diagnosis", "competitive_landscape", "sameness_patterns", "audience_tensions"],
 "outputs": ["positioning_problem", "required_positioning_shift"],
 "so_what_test": "Does this show the gap between what the business says and what the market hears?"
}


SLIDE 18 — STRATEGIC POSITIONING
{
 "slide_no": 18,
 "slide_name": "Strategic Positioning",
 "act": "Act 4 — Positioning and Narrative Answer",
 "purpose": "Define how the brand should compete in a simple, memorable and defensible form.",
 "visual_type": "we_are_we_are_not_framework",
 "layout_type": "A",
 "content_requirements": ["We are", "For", "Against", "Because", "Commercial role of the position"],
 "inputs": ["market_gap", "growth_audience", "positioning_problem", "proof_points"],
 "outputs": ["positioning_statement", "competitive_stance"],
 "so_what_test": "Could a competitor truthfully claim this? If yes, sharpen it."
}


SLIDE 19 — POSITIONING MAP
{
 "slide_no": 19,
 "slide_name": "Positioning Map",
 "act": "Act 4 — Positioning and Narrative Answer",
 "purpose": "Show where the brand should sit relative to competitors and why that space is ownable.",
 "visual_type": "positioning_map",
 "layout_type": "C",
 "content_requirements": ["Two strategic axes", "Competitor positions", "Current client position", "Recommended future position", "Ownable territory"],
 "inputs": ["axis_1", "axis_2", "competitor_positions", "client_position", "recommended_position"],
 "outputs": ["positioning_map", "ownable_territory"],
 "so_what_test": "Do the axes reveal real strategic tension rather than generic premium/value clichés?"
}


SLIDE 20 — NARRATIVE PLATFORM
{
 "slide_no": 20,
 "slide_name": "Narrative Platform",
 "act": "Act 4 — Positioning and Narrative Answer",
 "purpose": "Convert the positioning into the central story the market can understand and remember.",
 "visual_type": "narrative_platform_framework",
 "layout_type": "B",
 "content_requirements": ["Tension", "Shift", "Resolution", "Role of brand", "Core narrative line"],
 "inputs": ["strategic_tension", "market_shift", "brand_role", "positioning_statement"],
 "outputs": ["narrative_platform", "core_narrative"],
 "so_what_test": "Is this a story the company can operate from, not just a campaign line?"
}


SLIDE 21 — CORE MESSAGE ARCHITECTURE
{
 "slide_no": 21,
 "slide_name": "Core Message Architecture",
 "act": "Act 4 — Positioning and Narrative Answer",
 "purpose": "Translate the narrative into master message, supporting messages, proof points and objections to overcome.",
 "visual_type": "message_architecture",
 "layout_type": "C",
 "content_requirements": ["Master message", "Supporting messages", "Proof points", "Objections", "Response logic"],
 "inputs": ["narrative_platform", "proof_points", "audience_barriers", "category_entry_points"],
 "outputs": ["message_architecture", "proof_system"],
 "so_what_test": "Can a marketer brief a campaign from this without asking what the brand stands for?"
}


SLIDE 22 — MESSAGING TERRITORIES / DISTINCTIVE ASSETS
{
 "slide_no": 22,
 "slide_name": "Messaging Territories / Distinctive Assets",
 "act": "Act 4 — Positioning and Narrative Answer",
 "purpose": "Define flexible messaging territories and the distinctive assets that should become recognisable and compound over time.",
 "visual_type": "territory_and_asset_system",
 "layout_type": "D",
 "content_requirements": ["3-5 territories", "Strategic role", "Audience tension addressed", "Proof points", "Visual assets", "Verbal assets", "Tone/sonic/motion cues", "Recurring formats"],
 "inputs": ["message_architecture", "audience_tensions", "proof_points", "existing_assets", "brand_guidelines", "competitor_codes"],
 "outputs": ["messaging_territories", "distinctive_asset_system", "campaign_briefing_territories"],
 "so_what_test": "Can campaigns roam without the brand losing coherence or recognisability?"
}


SLIDE 23 — COMMERCIAL PRIZE
{
 "slide_no": 23,
 "slide_name": "Commercial Prize",
 "act": "Act 5 — The Growth System",
 "purpose": "Quantify what the recommended strategic shift could be worth so the founder sees money, not just positioning.",
 "visual_type": "commercial_opportunity_model",
 "layout_type": "F",
 "content_requirements": ["Current market size", "Current brand/category share where available", "Expanded addressable audience", "1/3/5% scenario model or equivalent", "Revenue implication", "Assumptions and caveats"],
 "inputs": ["market_size", "current_sales", "average_order_value", "gross_margin", "addressable_audience", "penetration_assumptions", "conversion_assumptions"],
 "outputs": ["commercial_prize", "growth_scenarios", "founder_value_case"],
 "so_what_test": "If the strategy is right, does the founder understand what it could be worth?"
}


SLIDE 24 — ATTENTION STRATEGY
{
 "slide_no": 24,
 "slide_name": "Attention Strategy",
 "act": "Act 5 — The Growth System",
 "purpose": "Define how the brand avoids invisibility and earns memory in fragmented media.",
 "visual_type": "attention_framework",
 "layout_type": "A",
 "content_requirements": ["Attention challenge", "Memory principle", "Context principle", "Distinctiveness principle", "Specific attention advantage", "Evidence for the importance of distinctive/interesting work"],
 "inputs": ["media_behaviour", "channel_data", "distinctive_assets", "category_entry_points", "attention_risks"],
 "outputs": ["attention_strategy", "memory_advantage"],
 "so_what_test": "What will people actually notice, remember and connect?"
}


SLIDE 25 — CHANNEL ROLES
{
 "slide_no": 25,
 "slide_name": "Channel Roles",
 "act": "Act 5 — The Growth System",
 "purpose": "Assign each channel a strategic role rather than choosing channels by habit or demographic shorthand.",
 "visual_type": "channel_role_map",
 "layout_type": "C",
 "content_requirements": ["Channel", "Strategic role", "Audience moment", "Content job", "Measurement signal", "Hand-off to next channel"],
 "inputs": ["recommended_channels", "audience_behaviour", "journey_context", "content_types", "measurement_data"],
 "outputs": ["channel_roles", "channel_ecosystem"],
 "so_what_test": "Does every channel have a clear job and do the jobs add up to growth?"
}


SLIDE 26 — CONTENT / CAMPAIGN SYSTEM
{
 "slide_no": 26,
 "slide_name": "Content / Campaign System",
 "act": "Act 5 — The Growth System",
 "purpose": "Show how the narrative becomes repeatable campaigns, assets and publishing rhythms.",
 "visual_type": "campaign_system_flow",
 "layout_type": "E",
 "content_requirements": ["Narrative", "Themes", "Campaigns", "Assets", "Distribution", "Optimisation loop"],
 "inputs": ["narrative_platform", "messaging_territories", "channel_roles", "asset_types", "publishing_cadence"],
 "outputs": ["campaign_system", "content_operating_model"],
 "so_what_test": "Can this produce a year of coherent activity without becoming repetitive?"
}


SLIDE 27 — CREATIVE DIRECTION / NEXT-PHASE HOOK
{
 "slide_no": 27,
 "slide_name": "Creative Direction / Next-Phase Hook",
 "act": "Act 5 — The Growth System",
 "purpose": "Make the strategic direction tangible without giving away full creative execution. Translate positioning into distinctive creative worlds that build memory, trust and conversion while preserving strategic coherence.",
 "visual_type": "creative_direction_cards",
 "layout_type": "D",
 "content_requirements": ["3-5 creative territories", "What it looks like", "What it feels like", "Commercial job", "Example formats", "Reference world", "Paid next-step CTA"],
 "inputs": ["messaging_territories", "distinctive_assets", "audience_tensions", "brand_aesthetic", "creative_routes"],
 "outputs": ["creative_direction", "next_phase_scope", "prototype_hook"],
 "so_what_test": "Do the creative territories strengthen memory, trust and distinctiveness while remaining strategically coherent and ownable?"
}


SLIDE 28 — CONSTRAINT PRIORITISATION / 90-DAY ACTIVATION PLAN
{
 "slide_no": 28,
 "slide_name": "Growth Priorities / 90-Day Activation Plan",
 "act": "Act 6 — Implementation and Measurement",
 "purpose": "Identify the highest-impact growth dependencies and sequence them into a practical 90-day plan. Marketing, operational and customer-experience priorities may all appear where they materially affect growth.",
 "visual_type": "constraint_priority_roadmap",
 "layout_type": "F",
 "content_requirements": ["Constraint list", "Impact", "Ease of fix", "Fix first / next / later", "First 30 days: foundation", "Days 31-60: launch", "Days 61-90: scale", "Owners", "Outputs", "Decision points"],
 "inputs": ["growth_constraint", "secondary_constraints", "strategic_priorities", "resources", "channels", "campaign_system", "client_capacity"],
 "outputs": ["constraint_priorities", "activation_roadmap", "first_90_days"],
 "so_what_test": "Does this clearly identify the highest-leverage growth priorities and the order they should be addressed?"
}


SLIDE 29 — ECONOMIC PRIORITISATION / MEASUREMENT FRAMEWORK
{
 "slide_no": 29,
 "slide_name": "Measurement Framework",
 "act": "Act 6 — Implementation and Measurement",
 "purpose": "Define how progress will be measured, reviewed and acted upon. This slide exists purely to establish the measurement and learning system.",
 "visual_type": "priority_matrix_plus_measurement_stack",
 "layout_type": "F",
 "content_requirements": ["Leading indicators", "Performance indicators", "Brand signals", "Learning cadence", "Decision rules", "Scale / stop / optimise triggers"],
 "inputs": ["business_objectives", "channel_roles", "campaign_system", "available_data", "measurement_tools", "budget_range", "client_capacity"],
 "outputs": ["economic_prioritisation", "measurement_framework", "learning_system"],
 "so_what_test": "Would a founder know whether the strategy is working, what to optimise and when to scale investment?"
}


SLIDE 30 — STRATEGIC PRINCIPLE / CLOSING MANDATE
{
 "slide_no": 30,
 "slide_name": "Strategic Principle / Closing Mandate",
 "act": "Act 6 — Implementation and Measurement",
 "purpose": "Close with the one principle that captures the required shift and gives the client conviction.",
 "visual_type": "closing_mandate",
 "layout_type": "B",
 "content_requirements": ["One memorable principle", "Summary of required shift", "Immediate next action", "Recommended paid next phase", "Narratiive contact / CTA"],
 "inputs": ["executive_thesis", "strategic_positioning", "activation_roadmap", "creative_direction_next_step"],
 "outputs": ["closing_mandate", "next_action", "paid_follow_on_path"],
 "so_what_test": "Does the deck end with conviction and a natural next commercial step?"
}


================ POPULATION RULES ================
1. Every slide must contain evidence → insight → interpretation → implication.
2. Every major diagnosis slide must attempt to include three evidence layers: Founder Believes, Evidence Shows, Customer Says.
3. No generic strategy. The client should think: "I did not know that" or "I have never seen our business explained that way."
4. Every recommendation must answer: why does this matter commercially?
5. Avoid marketing jargon, consultancy clichés and obvious observations.
6. Distinctiveness test: the slide must be unusable for a competitor.
7. Visuals, not paragraphs: each slide should carry one framework, model, map, table, comparison or evidence board.
8. The 30-slide Blueprint is the master product. The 5-slide and 10-slide versions are compressed views generated from the master, never substitutes for it.
9. Each slide should have a single job. If two ideas are fighting for space, split the thinking or cut one.
10. The work should feel like intelligence turned into action: market → audience → positioning → narrative → system → implementation.
11. The final output must help a founder or CMO make better decisions immediately.
12. Customer evidence must be treated as a credibility layer, not decoration. Use real reviews, comments, search behaviours, sales objections or interview language wherever possible.
13. Audience segments must be grounded in behaviour, motivation, barriers and commercial value. Avoid persona fiction.
14. Commercial prize modelling can use transparent assumptions where perfect data is unavailable, but assumptions must be stated clearly.
15. Creative Direction must not become free creative development. Do not create finished campaign concepts, polished mock-ups, production-ready scripts, finished art direction or full storyboards inside the Blueprint.
16. The Creative Direction slide should create appetite for the paid next phase: creative treatment, campaign platform development, prototyping, Canva/Higgsfield/Sora visual exploration and production planning.
17. Prioritisation must be explicit. Growth Priorities (Slide 28) owns prioritisation. Measurement Framework (Slide 29) owns measurement. Avoid duplicating prioritisation logic across both slides.


================ CREATIVE DIRECTION RULE ================
Creative prototypes are not part of the default Blueprint deliverable. The Blueprint may describe the creative world, emotional texture, reference universe, likely formats and commercial job of each territory. It should not fully execute the campaign.


Default wording for Slide 27:
"This is the strategic creative direction, not the finished creative treatment. The next phase turns these territories into campaign routes, visual prototypes, copy systems and production-ready assets."


================ DERIVATIVE OUTPUT MAPS ================
5-slide Executive Summary:
1. Growth Thesis — generated from slides 2, 3 and 30.
2. Market Reality — generated from slides 4, 5 and 8.
3. Growth Constraint — generated from slides 7, 9, 10 and 13.
4. Strategic Answer — generated from slides 18, 20, 21 and 22.
5. Commercial Plan — generated from slides 23, 28 and 29.


10-slide Diagnostic Teaser:
1. Cover — from slide 1.
2. Market Reality — from slides 4 and 5.
3. Sea of Sameness — from slide 7.
4. Growth Constraint — from slides 9 and 10.
5. Audience Opportunity — from slides 11 and 12.
6. Customer Evidence / Category Entry Points — from slides 13 and 15.
7. Positioning Gap — from slides 16 and 17.
8. Strategic Opportunity — from slides 8 and 18.
9. What We Would Build — from slides 20, 22, 26 and 27.
10. Next Step — from slides 28, 29 and 30.


================ CHANGE LOG FROM v2 TO v3 ================
1. Preserved the 30-slide limit.
2. Added Customer Evidence Board as Slide 13.
3. Merged Audience Tensions and Buyer Journey into Slide 14 to make space.
4. Merged Messaging Territories and Distinctive Assets into Slide 22 to make space.
5. Added Commercial Prize as Slide 23.
6. Reframed Creative Lookbook as Creative Direction / Next-Phase Hook on Slide 27.
7. Added Constraint Prioritisation into Slide 28.
8. Added Economic Prioritisation into Slide 29.
9. Strengthened population rules around founder credibility, commercial modelling and paid follow-on creative prototyping.
