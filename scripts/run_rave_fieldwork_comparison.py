from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.tony_claude_api_dispatcher import build_claude_api_dispatcher
from runtime.workflow_instructions import workflow_instruction
from runtime.workflow_registry import RESEARCH_TO_GROWTH_BLUEPRINT


SOURCE_FILES = (
    "rave-owned-surface.md",
    "market-and-competition.md",
    "customer-signals.md",
    "accounts-and-scale.md",
    "claim-consistency-and-operations.md",
    "channel-and-proposition-options.md",
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _research_pack(root: Path) -> dict[str, Any]:
    sources = []
    for name in SOURCE_FILES:
        path = root / name
        content = path.read_text(encoding="utf-8")
        sources.append(
            {
                "source_id": name.removesuffix(".md"),
                "captured_at": "2026-09-06",
                "status": "archived_public_evidence_requires_current_revalidation",
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "content": content,
            }
        )
    return {
        "pack_id": "rave-identical-research-comparison-20261017",
        "purpose": "Internal unsolicited FIELDWORK quality comparison; no Rave contact.",
        "evidence_status": "frozen comparison input, not current client evidence",
        "sources": sources,
    }


def _response_text(payload: dict[str, Any]) -> str:
    return "\n".join(
        str(block.get("text") or "").strip()
        for block in payload.get("content", [])
        if isinstance(block, dict) and block.get("type") == "text" and str(block.get("text") or "").strip()
    )


def _parse_json(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines.pop()
        candidate = "\n".join(lines).strip()
    value = json.loads(candidate)
    if not isinstance(value, dict):
        raise ValueError("Claude comparison response must be a JSON object")
    return value


def _direct_commission(evidence_pack: dict[str, Any]) -> dict[str, Any]:
    model = os.environ["TONY_DISPATCH_CLAUDE_MODEL"]
    api_key = os.environ.get("TONY_DISPATCH_CLAUDE_API_KEY") or os.environ["ANTHROPIC_API_KEY"]
    url = os.environ.get("TONY_DISPATCH_CLAUDE_API_URL", "https://api.anthropic.com/v1/messages")
    version = os.environ.get("TONY_DISPATCH_CLAUDE_API_VERSION", "2023-06-01")
    timeout = int(os.environ.get("TONY_DISPATCH_CLAUDE_TIMEOUT_SECONDS", "180"))
    prompt = """You are the senior strategy director for Narratiive's FIELDWORK product.

Use only the frozen Rave Coffee research pack below. This is an internal unsolicited exercise: Rave is not a client and must not be contacted. The source material was captured on 6 September 2026 and must not be represented as current without revalidation.

Commission: create a persuasive five-slide opening for a founder. The five slides must show, in order: (1) the founder's current position, (2) a credible 12-month commercial opportunity, (3) the growth levers, (4) the audience opportunity, and (5) the strategic direction. Build one cumulative argument. Use plain, confident English. Every slide must add a new fact, insight or decision. Do not use generic consultancy language. Do not invent revenue, forecasts, budgets, market shares, customer attitudes or internal performance. Where internal baseline data is absent, express the commercial opportunity as a transparent lever equation with client-replaceable variables and validation requirements, not a numerical forecast. Distinguish fact, interpretation and hypothesis. Earn the strategic direction from the evidence; do not merely copy the historic phrase 'de-snobbed speciality'.

Return exactly one JSON object with: central_argument; five_slide_opening (exactly five objects with slide_number, job, headline, body, evidence, commercial_implication, visual_direction, validation_needed); strategic_quality_notes; and evidence_limits. Return no markdown fences or commentary.

FROZEN RESEARCH PACK
""" + json.dumps(evidence_pack, sort_keys=True)
    payload = {
        "model": model,
        "max_tokens": int(os.environ.get("TONY_DISPATCH_CLAUDE_GROWTH_BLUEPRINT_MAX_TOKENS", "32768")),
        "messages": [{"role": "user", "content": prompt}],
    }
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-api-key": api_key,
            "anthropic-version": version,
        },
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:  # nosec B310 - operator-configured Anthropic endpoint
        returned = json.loads(response.read().decode("utf-8") or "{}")
    if returned.get("stop_reason") == "max_tokens":
        raise RuntimeError("direct Claude comparison was truncated")
    result = _parse_json(_response_text(returned))
    result["_execution"] = {
        "provider": "anthropic",
        "model": returned.get("model") or model,
        "provider_message_id": returned.get("id", ""),
        "stop_reason": returned.get("stop_reason", ""),
    }
    return result


def _tony_commission(evidence_pack: dict[str, Any]) -> dict[str, Any]:
    stage = RESEARCH_TO_GROWTH_BLUEPRINT.stages[0]
    expected = tuple(stage.output_contract.required_fields)
    dispatcher = build_claude_api_dispatcher(os.environ)
    target = {
        "evidence_pack": evidence_pack,
        "approved_growth_sprint_scope": {
            "status": "comparison_only_not_client_approved",
            "question": "Where can Rave Coffee create more controllable, compounding growth over the next 12 months?",
            "constraints": ["No contact", "No invented internal data", "No external action"],
        },
        "client_context": {
            "company_name": "Rave Coffee",
            "relationship": "internal unsolicited exercise; not a client",
        },
        "workflow_context": {
            "workflow_id": "research_to_growth_blueprint",
            "stage_id": stage.stage_id,
            "expected_outputs": list(expected),
            "side_effect_classification": "preparation",
        },
    }
    return dispatcher(
        {
            "worker": "Claude",
            "execution_mode": "autonomous_prepare",
            "eligible": True,
            "state": "ready_for_autonomous_dispatch",
            "execution_truth": "not_dispatched",
            "instruction": workflow_instruction("research_to_growth_blueprint", stage.stage_id, expected),
            "target": target,
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    evidence_pack = _research_pack(args.research_root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(args.output_dir / "identical-rave-research-pack.json", evidence_pack)
    direct = _direct_commission(evidence_pack)
    _write_json(args.output_dir / "direct-claude-five-slide-opening.json", direct)
    tony = _tony_commission(evidence_pack)
    _write_json(args.output_dir / "tony-pipeline-strategic-draft.json", tony)
    _write_json(
        args.output_dir / "comparison-execution.json",
        {
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "research_pack_sha256": hashlib.sha256(
                json.dumps(evidence_pack, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "same_provider_model": direct.get("_execution", {}).get("model") == tony.get("model"),
            "direct": direct.get("_execution", {}),
            "tony": {
                "provider": tony.get("provider", ""),
                "model": tony.get("model", ""),
                "provider_message_id": tony.get("provider_message_id", ""),
                "stop_reason": tony.get("stop_reason", ""),
            },
            "external_action_taken": False,
        },
    )


if __name__ == "__main__":
    main()
