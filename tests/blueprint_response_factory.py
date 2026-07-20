from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _join_lines(lines: Sequence[str]) -> str:
    return "\n".join(line for line in lines if line).rstrip()


def _special_slide_content(slide_no: int, slide_name: str, act_name: str, layout_type: str) -> dict[str, list[str]]:
    thesis = [f"{slide_name} advances the strategic case for {act_name.lower()}."]
    founder_insight = [f"Founder insight for slide {slide_no} turns the point into a commercial reason to act."]
    so_what = [f"So what: {slide_name} makes the next decision clearer."]
    source_notes = [f"- ev_{slide_no:02d}_a supports {slide_name.lower()}."]
    visual_direction = [f"Visual / Layout Direction: Use a {layout_type}-style layout with editorial hierarchy."]
    speaker_notes = [f"Speaker Notes: Keep the strategic implication of {slide_name.lower()} explicit."]

    if slide_no == 1:
        thesis = ["RAVE should be positioned as the coffee brand that turns routine into a deliberate ritual."]
        founder_insight = [
            "The commercial tension is not taste versus price; it is routine versus meaning.",
        ]
        so_what = ["The Blueprint needs to make the business case for premium routine."]
        source_notes = [
            "- ev_deadbeef supports the routine-over-commodity framing.",
            "- ev_cafebabe supports the premium routine commercial question.",
        ]
        visual_direction = [
            "Visual / Layout Direction: Open with a bold thesis spread and a single commercial question set in spacious editorial type.",
        ]
        speaker_notes = ["Speaker Notes: Frame the document as a premium strategic product."]
    elif slide_no == 12:
        thesis = ["Audience segments should be discovered as behavioural demand pools, not demographic buckets."]
        founder_insight = [
            "Behavioural labels such as Weekend Ritualist, Supermarket-Plus Switcher and Subscription Sceptic are more useful than generic personas.",
        ]
        so_what = ["The audience model should be built around observed routines, not stereotypes."]
        source_notes = [
            "- ev_deadbeef supports the behavioural demand pool lens.",
            "- ev_cafebabe supports the demand-pool language choice.",
        ]
        visual_direction = [
            "Visual / Layout Direction: Use concentric demand-pool rings with evidence chips.",
        ]
        speaker_notes = ["Speaker Notes: Explain why behavioural definitions beat demographic categories."]
    elif slide_no == 27:
        thesis = ["Creative direction should make the strategic platform tangible without giving away full execution."]
        founder_insight = ["Creative territories should build memory, trust and conversion while preserving strategic coherence."]
        so_what = ["The next phase should feel designed, not generic."]
        source_notes = ["- ev_cafebabe supports the creative direction hook."]
        visual_direction = ["Visual / Layout Direction: Use a grid of creative territories and a bold next-step hook."]
        speaker_notes = ["Speaker Notes: Keep the hook high level and protect execution detail."]
    elif slide_no == 28:
        thesis = ["Separate growth priorities from dependencies so the plan remains actionable."]
        founder_insight = [
            "Some recommendations live outside marketing but still determine retention, LTV and media effectiveness.",
        ]
        so_what = ["The plan should make the minimum set of commitments visible."]
        source_notes = ["- ev_cafebabe supports the growth priorities and dependencies split."]
        visual_direction = ["Visual / Layout Direction: Use a two-column matrix with priorities on the left and dependencies on the right."]
        speaker_notes = ["Speaker Notes: Distinguish marketing-controlled actions from cross-functional dependencies."]
    elif slide_no == 29:
        thesis = ["Measure the system through leading indicators, performance signals and learning loops."]
        founder_insight = ["The measurement frame should explain what to watch, when to act, and how to learn."]
        so_what = ["The founder should know whether the strategy is working without reading a dashboard spec."]
        source_notes = ["- ev_deadbeef supports the measurement and learning framework."]
        visual_direction = ["Visual / Layout Direction: Show a stacked measurement view with a calm priority matrix."]
        speaker_notes = ["Speaker Notes: Close the deck with decision rules rather than prioritisation logic."]
    elif slide_no == 30:
        thesis = ["The closing mandate should point to the one principle that captures the required shift."]
        founder_insight = ["The closing line should give the client conviction and an immediate next commercial step."]
        so_what = ["If RAVE owns the emotional role of the morning ritual, it has a defensible reason to exist beyond taste alone."]
        source_notes = [
            "- ev_deadbeef supports the closing conviction.",
            "- ev_cafebabe supports the commercial next step.",
            f"- ev_{slide_no:02d}_a supports the closing recommendation.",
        ]
        visual_direction = ["Visual / Layout Direction: End with a bold, minimal closing slide ready to hand directly into production."]
        speaker_notes = ["Speaker Notes: End with conviction rather than elaboration."]

    return {
        "thesis": thesis,
        "founder_insight": founder_insight,
        "so_what": so_what,
        "source_notes": source_notes,
        "visual_direction": visual_direction,
        "speaker_notes": speaker_notes,
    }


def render_slide_block(
    slide,
    *,
    slide_heading: str | None = None,
    extra_sections: Sequence[tuple[str, str]] = (),
) -> str:
    heading = slide_heading or f"Slide {slide.slide_no} — {slide.slide_name}"
    content = _special_slide_content(slide.slide_no, slide.slide_name, slide.act, slide.layout_type)
    parts = [f"### {heading}"]
    for section_name, body_lines in (
        ("Thesis", content["thesis"]),
        ("Founder Insight", content["founder_insight"]),
        ("So What", content["so_what"]),
        ("Source Notes", content["source_notes"]),
        ("Visual / Layout Direction", content["visual_direction"]),
        ("Speaker Notes", content["speaker_notes"]),
    ):
        body = _join_lines(body_lines)
        if body:
            parts.append(f"\n#### {section_name}\n{body}")
    for heading, body in extra_sections:
        if body.strip():
            parts.append(f"\n#### {heading}\n{body.strip()}")
    return "\n".join(parts)


def render_canonical_blueprint_markdown(
    schema,
    *,
    wrapped: bool = True,
    title: str = "RAVE Blueprint",
    act_heading_overrides: Mapping[int, str] | None = None,
    slide_heading_overrides: Mapping[int, str] | None = None,
    missing_slide_numbers: Sequence[int] = (),
    duplicate_slide_numbers: Sequence[int] = (),
    extra_sections_by_slide: Mapping[int, Sequence[tuple[str, str]]] | None = None,
) -> str:
    act_heading_overrides = dict(act_heading_overrides or {})
    slide_heading_overrides = dict(slide_heading_overrides or {})
    extra_sections_by_slide = dict(extra_sections_by_slide or {})
    missing = {int(item) for item in missing_slide_numbers}
    duplicate = {int(item) for item in duplicate_slide_numbers}
    chunks: list[str] = []
    if wrapped:
        chunks.append(f"# {title}\n")
    for act_index, act_name in enumerate(schema.acts, start=1):
        rendered_act_name = act_heading_overrides.get(act_index, act_name)
        chunks.append(f"## {rendered_act_name}")
        for slide in [item for item in schema.slides if item.act == act_name or (act_index == 1 and item.slide_no == 1)]:
            if slide.slide_no in missing:
                continue
            slide_heading = slide_heading_overrides.get(slide.slide_no, f"Slide {slide.slide_no} — {slide.slide_name}")
            chunks.append(
                render_slide_block(
                    slide,
                    slide_heading=slide_heading,
                    extra_sections=extra_sections_by_slide.get(slide.slide_no, ()),
                )
            )
            if slide.slide_no in duplicate:
                chunks.append(
                    render_slide_block(
                        slide,
                        slide_heading=slide_heading,
                        extra_sections=extra_sections_by_slide.get(slide.slide_no, ()),
                    )
                )
    return "\n\n".join(chunks).strip() + "\n"
