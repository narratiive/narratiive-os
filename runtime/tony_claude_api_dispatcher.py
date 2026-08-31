from __future__ import annotations

import json
from typing import Any, Mapping
from urllib import request


DEFAULT_ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_API_URL = "https://api.anthropic.com/v1/messages"


class ClaudeDispatcherConfigError(RuntimeError):
    pass


def build_claude_api_dispatcher(environ: Mapping[str, str]):
    """Build an explicit Anthropic Messages API dispatcher for safe Claude preparation.

    This surface is intentionally limited to Tony contracts already classified as
    autonomous preparation. It cannot be used for Gmail sends, Calendar writes,
    Notion mutations, or any other consequential external action.
    """
    api_key = str(environ.get("TONY_DISPATCH_CLAUDE_API_KEY") or environ.get("ANTHROPIC_API_KEY") or "").strip()
    model = str(environ.get("TONY_DISPATCH_CLAUDE_MODEL") or "").strip()
    api_url = str(environ.get("TONY_DISPATCH_CLAUDE_API_URL") or DEFAULT_API_URL).strip()
    version = str(environ.get("TONY_DISPATCH_CLAUDE_API_VERSION") or DEFAULT_ANTHROPIC_VERSION).strip()
    max_tokens_raw = str(environ.get("TONY_DISPATCH_CLAUDE_MAX_TOKENS") or "4096").strip()

    if not api_key:
        raise ClaudeDispatcherConfigError("Claude API dispatch requires ANTHROPIC_API_KEY or TONY_DISPATCH_CLAUDE_API_KEY")
    if not model:
        raise ClaudeDispatcherConfigError("Claude API dispatch requires TONY_DISPATCH_CLAUDE_MODEL")
    try:
        max_tokens = int(max_tokens_raw)
    except ValueError as exc:
        raise ClaudeDispatcherConfigError("TONY_DISPATCH_CLAUDE_MAX_TOKENS must be an integer") from exc
    if max_tokens <= 0:
        raise ClaudeDispatcherConfigError("TONY_DISPATCH_CLAUDE_MAX_TOKENS must be greater than zero")

    def dispatch(contract: dict[str, Any]) -> dict[str, Any]:
        _validate_safe_contract(contract)
        prompt = _render_prompt(contract)
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            api_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-api-key": api_key,
                "anthropic-version": version,
            },
            method="POST",
        )
        with request.urlopen(req, timeout=90) as response:  # nosec B310 - Anthropic URL is explicit operator config
            raw = response.read().decode("utf-8")
        returned = json.loads(raw or "{}")
        if not isinstance(returned, dict):
            raise RuntimeError("Claude API response must be a JSON object")
        if returned.get("error"):
            raise RuntimeError(f"Claude API returned an error: {returned['error']}")

        text = _response_text(returned)
        if not text:
            raise RuntimeError("Claude API returned no text work product")
        evidence = _parse_work_product(text)
        evidence.setdefault("work_product", text)
        evidence["verified"] = True
        evidence["provider"] = "anthropic"
        if returned.get("id"):
            evidence["provider_message_id"] = str(returned["id"])
        evidence["model"] = str(returned.get("model") or model)
        evidence["stop_reason"] = str(returned.get("stop_reason") or "")
        return evidence

    return dispatch


def _validate_safe_contract(contract: Mapping[str, Any]) -> None:
    if str(contract.get("worker") or "").strip().casefold() != "claude":
        raise RuntimeError("Claude dispatcher received a contract for another worker")
    if str(contract.get("execution_mode") or "").strip() != "autonomous_prepare":
        raise RuntimeError("Claude API dispatcher only permits autonomous_prepare contracts")
    if contract.get("eligible") is not True or contract.get("state") != "ready_for_autonomous_dispatch":
        raise RuntimeError("Claude preparation contract is not eligible for autonomous dispatch")
    if contract.get("execution_truth") != "not_dispatched":
        raise RuntimeError("Claude preparation contract has already left the not-dispatched state")


def _render_prompt(contract: Mapping[str, Any]) -> str:
    action = str(contract.get("instruction") or contract.get("action") or "").strip()
    target = contract.get("target") if isinstance(contract.get("target"), Mapping) else {}
    return (
        "You are the Claude execution worker inside Narratiive OS. Complete only the bounded internal preparation task below.\n\n"
        "SAFETY BOUNDARY\n"
        "- Do not send email, create calendar events, update Notion, publish, deploy, purchase, or mutate any external system.\n"
        "- Do not claim an external action happened.\n"
        "- Preserve uncertainty and evidence gaps.\n"
        "- Use only evidence supplied in the task or sources you can genuinely verify within your available research capability.\n\n"
        f"TASK\n{action}\n\n"
        f"TARGET CONTEXT\n{json.dumps(dict(target), sort_keys=True)}\n\n"
        "RETURN CONTRACT\n"
        "Return exactly one JSON object and no markdown fences. Use task-specific fields where appropriate. "
        "For Blueprint Lite work, follow the canonical inbound product boundary: diagnostic inputs must be represented faithfully; "
        "separate facts, interpretations and hypotheses; include selective outside-in evidence; identify one company-specific growth tension; "
        "offer one consequential but provisional opportunity; include meaningful questions to answer next; and stop at a human-review-ready internal artefact. "
        "Return blueprint_lite, source_backed_evidence (or sources), evidence_gaps, fact_interpretation_hypothesis_lineage, "
        "growth_tension, provisional_opportunity, questions_to_answer_next, quality_gate, and recommendation containing advance, revise, or stop. "
        "Do not turn Blueprint Lite into the paid Growth Blueprint, a proposal, or a client send. "
        "For Growth Blueprint work, include growth_blueprint, sources (or source_backed_evidence), evidence_gaps, narratiive_fit, "
        "strategic_growth_opportunity, and recommendation containing advance, revise, or stop. "
        "For outreach preparation, include email_subject, email_body, and optional creative_brief. "
        "For meeting or proposal preparation, return the requested draft plus the evidence basis. "
        "Always include at least one substantive work-product field such as work_product, draft, content, analysis, recommendation, or result."
    )


def _response_text(payload: Mapping[str, Any]) -> str:
    blocks = payload.get("content")
    if not isinstance(blocks, list):
        return ""
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, Mapping) and block.get("type") == "text":
            text = str(block.get("text") or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def _parse_work_product(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return {"work_product": text}
    if not isinstance(parsed, dict) or not parsed:
        return {"work_product": text}
    return dict(parsed)
