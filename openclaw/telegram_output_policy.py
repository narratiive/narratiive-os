from __future__ import annotations

import re


TELEGRAM_SAFE_CHARACTERS = 3500

_ARTEFACT_NAMES = (
    "blueprint lite",
    "discovery synthesis",
    "growth sprint proposal",
    "strategy thesis",
    "growth blueprint",
    "campaign world",
    "creative director's bible",
    "substantial research report",
)
_HEADING = re.compile(r"(?m)^\s*(?:#{1,4}\s+|\*\*\s*(?:\d+\.|[A-Z][A-Z0-9 —&/-]{3,})|\d+\.\s+[A-Z])")


def protect_telegram_output(value: str) -> str:
    """Keep conversation in Telegram and long-form artefacts in their workflow.

    Semantic artefact detection is primary. The fixed envelope is a final Bot
    API safety net for non-artefact conversational output.
    """

    text = str(value or "").strip()
    lowered = text.casefold()
    named_artefact = any(name in lowered for name in _ARTEFACT_NAMES)
    structured_document = len(_HEADING.findall(text)) >= 4
    if len(text) >= 1400 and named_artefact and structured_document:
        return (
            "I’ve kept the full review artefact out of Telegram because this channel is for conversation and decisions. "
            "It has not been represented as emailed here. I need to persist the exact artefact in Narratiive OS, deliver the review copy through the internal-review route, and then return with the concise gate summary and verified delivery evidence."
        )
    if len(text) <= TELEGRAM_SAFE_CHARACTERS:
        return text
    suffix = "\n\nI’ve shortened this conversational reply to fit Telegram. Any full review artefact belongs in the internal review delivery channel."
    return text[: TELEGRAM_SAFE_CHARACTERS - len(suffix) - 1].rstrip() + "…" + suffix
