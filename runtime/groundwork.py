"""Groundwork's compact internal qualification contract, shared by both commissions."""
from collections.abc import Mapping
from datetime import date, datetime, timezone
import re
from urllib.parse import urlparse

WEIGHTS = {
    "Commercial potential": 30,
    "Marketing opportunity": 30,
    "Brand and creative potential": 20,
    "Narratiive fit": 20,
}

GROUNDWORK_INSTRUCTION = """
Also return prospect_intelligence as the internal Groundwork Prospect Intelligence Brief.
This is pre-Discovery qualification, never FIELDWORK or a comprehensive strategy report.
Keep the entire prospect_intelligence object to 450-650 words, including sources; the
renderer permits at most two A4 pages and aims for one. Use short, meaningful observations.
Return exactly these keys:
- assessed_on: YYYY-MM-DD (the supplied assessment date; do not invent today's date).
- verdict: a conclusion-led commercial judgement of 20-35 words.
- confidence: High, Medium or Low, followed by a short evidence-limit explanation.
- scorecard: exactly four objects, in this order, with criterion, score (integer),
  rationale (15-25 words, evidence-linked, identifying verified basis and assumptions):
  Commercial potential /30; Marketing opportunity /30; Brand and creative potential /20;
  Narratiive fit /20. This is Narratiive's prospect score, not the diagnostic score.
  Unknown budget, mandate, capacity and performance must constrain the score.
- company_and_people: 50-75 words on business model, scale/growth signals, founder's
  background and relevant leaders. Date historical signals; do not imply current growth.
- brand_character: 40-60 words interpreting personality, attitude, values, visual identity,
  voice and emotional character, and commercial/creative compatibility with Narratiive.
  Assess professional public behaviour, never infer private personality or intentions.
- marketing_examples: 2 or 3 strings, 25-40 words each, naming specific campaigns, paid ads,
  social content, collaborations, PR or ecommerce activity with checkable source [n].
- channel_limits: 20-35 words on channels not verified (including paid and social),
  recency and performance unknowns. An inaccessible ad library is not evidence of no ads.
- growth_hypotheses: 2 or 3 strings, 20-30 words each; label each Hypothesis, name the
  revenue/retention/acquisition mechanism, evidence basis and what needs validation.
- discovery_questions: exactly 3 substantive priority questions ending in ?.
- unknowns: 20-40 words, explicitly distinguishing assumptions from unknowns.
- sources: 1-8 objects (aim for at least 3 independent pages when supplied) with label (short title), url (verified public HTTP(S) URL),
  checked_on (supplied assessment date). Cite these in order as [1], [2], etc throughout.
Use only supplied verified evidence. If evidence is missing say unknown, reduce confidence,
and recommend further qualification or deprioritisation. Never invent financials, ad spend,
internal conversion, ROAS, agency relationships, founder intent or buying readiness.
The renderer computes the total and recommendation: 80-100 Priority prospect / pursue;
70-79 Qualify further / qualify; below 70 Do not prioritise / deprioritise. Scores are
advisory internal judgements, not authority to contact anyone or advance a workflow.
Include brand imagery only with recorded reuse permission; otherwise use typography.
Keep the existing Blueprint Lite fields and diagnostic evidence separate and intact.
"""


def validate_prospect_intelligence(value, *, verified_sources=None):
    """Reject malformed briefs rather than fabricate scores or silently truncate copy."""
    errors = []
    if not isinstance(value, Mapping):
        return ["prospect intelligence missing"]
    for key in ("assessed_on", "verdict", "confidence", "company_and_people", "brand_character", "channel_limits", "unknowns"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            errors.append(f"{key} missing")
    rows = value.get("scorecard")
    if not isinstance(rows, list) or len(rows) != 4:
        errors.append("four scorecard rows required")
    else:
        for row, (criterion, weight) in zip(rows, WEIGHTS.items()):
            if not isinstance(row, Mapping) or row.get("criterion") != criterion or type(row.get("score")) is not int or not 0 <= row["score"] <= weight or not isinstance(row.get("rationale"), str) or not row["rationale"].strip():
                errors.append(f"invalid {criterion} score")
    for key, low, high in (("marketing_examples", 2, 3), ("growth_hypotheses", 2, 3), ("discovery_questions", 3, 3)):
        items = value.get(key)
        if not isinstance(items, list) or not low <= len(items) <= high or not all(isinstance(x, str) and x.strip() for x in items):
            errors.append(f"invalid {key}")
        elif key == "discovery_questions" and not all(x.rstrip().endswith("?") for x in items):
            errors.append("discovery questions must be questions")
    if not str(value.get("confidence") or "").startswith(("High", "Medium", "Low")):
        errors.append("confidence must begin High, Medium or Low")
    sources = value.get("sources")
    if not isinstance(sources, list) or not 1 <= len(sources) <= 8:
        errors.append("one to eight sources required")
    else:
        for item in sources:
            if not isinstance(item, Mapping) or not all(isinstance(item.get(k), str) and item[k].strip() for k in ("label", "url", "checked_on")):
                errors.append("source metadata must be non-empty strings")
                continue
            try:
                date.fromisoformat(item["checked_on"])
                url = urlparse(item["url"])
                if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
                    errors.append("invalid source URL")
            except ValueError:
                errors.append("invalid source date or URL")
        if verified_sources is not None:
            allowed = set()
            def collect(node):
                if isinstance(node, Mapping):
                    for k, v in node.items():
                        if k in {"url", "uri", "source"} and isinstance(v, str):
                            allowed.add(v.rstrip("/"))
                        elif isinstance(v, (Mapping, list, tuple)):
                            collect(v)
                elif isinstance(node, (list, tuple)):
                    for v in node:
                        collect(v)
            collect(verified_sources)
            if any(not isinstance(item, Mapping) or str(item.get("url") or "").rstrip("/") not in allowed for item in sources):
                errors.append("brief sources must match supplied evidence URLs")
        citation_texts = []
        for key in ("company_and_people", "brand_character"):
            citation_texts.append(value.get(key))
        if isinstance(rows, list):
            citation_texts.extend(row.get("rationale") for row in rows if isinstance(row, Mapping))
        for key in ("marketing_examples", "growth_hypotheses"):
            if isinstance(value.get(key), list):
                citation_texts.extend(value[key])
        for text in citation_texts:
            if not isinstance(text, str):
                continue
            citations = re.findall(r"\[(\d+(?:[-,]\d+)*)\]", text)
            if not citations:
                errors.append("material observations require citations")
            for citation in citations:
                numbers = [int(n) for n in re.split(r"[-,]", citation)]
                if any(n < 1 or n > len(sources) for n in numbers):
                    errors.append("citation references a missing source")
    return errors


def qualification(value):
    total = sum(row["score"] for row in value["scorecard"])
    label, action = ("Priority prospect", "PURSUE") if total >= 80 else (("Qualify further", "QUALIFY") if total >= 70 else ("Do not prioritise", "DEPRIORITISE"))
    return total, label, action


def groundwork_instruction():
    return GROUNDWORK_INSTRUCTION + "\nAssessment date: " + datetime.now(timezone.utc).date().isoformat()
