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
    return text[:limit].rstrip()


def is_generic_founder_action(value: str) -> bool:
    return " ".join(str(value).casefold().split()).rstrip(".?!") in _GENERIC_ACTION
