"""Founder-safe presentation helpers; detailed evidence stays in the audit record."""

import re


_RUNTIME_REFERENCE = re.compile(
    r"\b(?:workflow(?:[_ ]?run)?|run[_ ]?id|workstream)\s*[:#-]?\s*[a-z0-9][a-z0-9_.-]{5,}\b",
    re.IGNORECASE,
)
_GITHUB_REFERENCE = re.compile(r"\b(?:pull request|pr|issue)\s*#?\d+\b", re.IGNORECASE)
_MACHINE_IDENTIFIER = re.compile(r"\b[a-z]+(?:_[a-z0-9]+){2,}\b", re.IGNORECASE)
_GENERIC_ACTION = {
    "review and decide this item",
    "review the lead and decide the next commercial action",
    "continue the current authorised internal workflow step",
}


def material_founder_lines(decisions: tuple[str, ...], risks: tuple[str, ...]) -> tuple[str, ...]:
    selected: list[str] = []
    for value in (*decisions, *risks):
        text = founder_text(value)
        if text and text not in selected:
            selected.append(text)
        if len(selected) == 3:
            break
    return tuple(selected)


def founder_text(value: str, *, limit: int = 260) -> str:
    """Strip implementation identifiers from a short founder-facing statement."""
    text = re.sub(r"\b(?:workstream:)?workflow:[^\s:]+:", "", str(value), flags=re.IGNORECASE)
    text = re.sub(r"\b(?:workflow_run|run_id|workstream):[^\s:]+:?", "", text, flags=re.IGNORECASE)
    text = _RUNTIME_REFERENCE.sub("", text)
    text = _GITHUB_REFERENCE.sub("engineering item", text)
    text = _MACHINE_IDENTIFIER.sub("", text)
    text = " ".join(text.split()).strip(" -:;.")
    if len(text) > limit:
        text = text[:max(0, limit - 1)].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"
    return text


def is_generic_founder_action(value: str) -> bool:
    return " ".join(str(value).casefold().split()).rstrip(".?!") in _GENERIC_ACTION


def decision_ready_materials(snapshot, *, pipeline=None) -> tuple[str, ...]:
    """Use the agency attention policy before interrupting, never raw IDs.

    No state is changed and technical evidence remains in Mission Control.
    Only an evidenced business blocker or a concrete human decision justifies
    an interruption.
    """
    from runtime.agency_state_projection import AgencyStateProjector
    from runtime.briefing_intelligence import ExecutiveBriefingPipeline

    state = (pipeline or ExecutiveBriefingPipeline()).refine(AgencyStateProjector().project(snapshot))
    lines = []
    for item in state.executive_items:
        if not (item.requires_matt or (item.blocked and item.blocks_agency_outcome)):
            continue
        title = founder_text(item.title, limit=130)
        reason = founder_text(item.why_matters, limit=220)
        action = founder_text(item.next_action, limit=240)
        line = f"{title}. {reason}. Recommended next step: {action}."
        if line not in lines:
            lines.append(line)
    return tuple(lines)


def render_material_update(materials: tuple[str, ...] | list[str]) -> str:
    """A complete bounded summary with a concrete route to the full queue."""
    lines = ["Tony — decisions and delivery risks"]
    selected = 0
    footer = "Ask me for the remaining decisions and delivery risks for the full queue."
    for item in materials:
        reserved_footer = f"{len(materials)} other business items remain in Mission Control. {footer}"
        candidate = "\n\n".join((*lines, item, reserved_footer))
        if len(candidate) > 3500:
            break
        lines.append(item)
        selected += 1
    if selected < len(materials):
        lines.append(f"{len(materials) - selected} other business items remain in Mission Control. {footer}")
    return "\n\n".join(lines)
