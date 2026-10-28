#!/usr/bin/env python3
"""Review rendered slide pixels and OCR output before a Blueprint can pass QA."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageFilter


def load_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def layout_signature(path: Path) -> tuple[float, ...]:
    image = Image.open(path).convert("L").resize((64, 36))
    edges = image.filter(ImageFilter.FIND_EDGES)
    values = [float(value) for value in edges.getdata()]
    for row in list(range(7)) + list(range(31, 36)):
        values[row * 64:(row + 1) * 64] = [0.0] * 64
    norm = math.sqrt(sum(value * value for value in values))
    return tuple(value / norm for value in values) if norm else tuple(values)


def similarity(left: Sequence[float], right: Sequence[float]) -> float:
    return float(sum(a * b for a, b in zip(left, right)))


def normalized_words(value: object) -> list[str]:
    return re.findall(r"[a-z0-9£]+", str(value or "").casefold())


def text_fragment(value: object, *, tail: bool = False, count: int = 5) -> str:
    words = normalized_words(value)
    selected = words[-count:] if tail else words[:count]
    return " ".join(selected)


def compact_copy(value: object, limit: int) -> str:
    content = re.sub(r"\s+", " ", str(value or "").replace("—", " - ").replace("–", " - ")).strip()
    if len(content) <= limit:
        return content
    prefix = content[:limit]
    sentence = max(prefix.rfind(". "), prefix.rfind("? "), prefix.rfind("! "))
    if sentence >= min(70, limit // 2):
        return prefix[:sentence + 1].strip()
    cut = prefix.rfind(" ")
    return content[:cut if cut > 24 else limit].rstrip(" ,;:") + "."


def rendered_copy_gaps(expected: list[dict], ocr_text: list[str], *, demonstration_profile: bool = False) -> list[dict]:
    """Find copy that the renderer contract says must be visible in the pixels."""
    body_layouts = {
        "single_thesis_page": 430, "question_frame": 430, "ecosystem_map_of_forces": 190,
        "sameness_audit": 330, "provocation_page": 245, "evidence_ladder": 300,
        "creative_principles": 95, "test_plan": 190,
    }
    gaps: list[dict] = []
    for index, slide in enumerate(expected, 1):
        if index > len(ocr_text) or not isinstance(slide, dict):
            gaps.append({"slide": index, "missing": ["rendered OCR"]})
            continue
        observed = " ".join(normalized_words(ocr_text[index - 1]))
        required: list[tuple[str, str]] = []
        if index != 1:
            required.append(("title", text_fragment(slide.get("title"))))
        if index not in (1, len(expected)) and not (
            demonstration_profile and slide.get("layout_type") == "source_register"
        ):
            required.append(("takeaway ending", text_fragment(compact_copy(slide.get("takeaway"), 210), tail=True)))
        body_limit = body_layouts.get(str(slide.get("layout_type") or ""))
        if index != 1 and body_limit:
            required.append(("body ending", text_fragment(compact_copy(slide.get("body"), body_limit), tail=True)))
        missing = [label for label, fragment in required if fragment and fragment not in observed]
        if missing:
            gaps.append({"slide": index, "missing": missing})
    return gaps


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("slides_dir", type=Path)
    parser.add_argument("specification", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--swift", default="/usr/bin/swift")
    parser.add_argument("--ocr-script", type=Path, required=True)
    args = parser.parse_args()

    spec = load_object(args.specification)
    demonstration_profile = "seven-chapter issue #471 demonstration profile" in str(
        spec.get("template_source") or ""
    ).casefold()
    founder_quality_profile = "issue #473 founder-quality controls" in str(
        spec.get("template_source") or ""
    ).casefold()
    fieldwork_v4_roles = (
        "commercial_position_today", "twelve_month_opportunity", "where_gains_come_from",
        "audience_opportunity", "strategic_direction",
    )
    fieldwork_v4_profile = tuple(
        str(((slide.get("content_data") or {}).get("fieldwork_role") or ""))
        for slide in (spec.get("slides") or [])[:5]
        if isinstance(slide, dict)
    ) == fieldwork_v4_roles
    slides = sorted(args.slides_dir.glob("slide-*.png"))
    expected = spec.get("slides") or []
    ocr_path = args.output.with_name("rendered-slide-ocr.json")
    subprocess.run(
        [args.swift, str(args.ocr_script), str(args.slides_dir), str(ocr_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    ocr = load_object(ocr_path).get("slides") or []
    ocr_text = [str(item.get("text") or "") for item in ocr if isinstance(item, dict)]
    image_sizes = [Image.open(path).size for path in slides]
    expected_size = image_sizes[0] if image_sizes else None

    signatures = [layout_signature(path) for path in slides]
    duplicate_pairs = []
    for left in range(len(signatures)):
        for right in range(left + 1, len(signatures)):
            score = similarity(signatures[left], signatures[right])
            if score >= 0.992:
                duplicate_pairs.append({"slides": [left + 1, right + 1], "similarity": round(score, 4)})

    truncated = []
    for index, content in enumerate(ocr_text, 1):
        if "…" in content or re.search(r"(?:\.{3}|\.\s+\.\s+\.)", content):
            truncated.append(index)

    progression_terms = (
        (
            "opportunity", "constraint", "advantage", "strategy", "creative",
            "growth engine", "12 months", "founder decision",
        )
        if founder_quality_profile
        else ("opportunity", "constraint", "advantage", "strategy", "creative", "growth engine", "12 months", "approval")
        if demonstration_profile
        else ("constraint", "proof", "audience", "position", "commercial", "creative", "source", "mandate")
    )
    combined = " ".join(ocr_text).casefold()
    progression_hits = [term for term in progression_terms if term in combined]
    source_slides = [
        index + 1 for index, slide in enumerate(expected)
        if isinstance(slide, dict) and bool((slide.get("content_data") or {}).get("source_register_entries"))
    ]
    model_slides = [
        index + 1 for index, slide in enumerate(expected)
        if isinstance(slide, dict) and slide.get("layout_type") == "commercial_model"
    ]
    citation_pattern = re.compile(
        r"\b(?:A\d+|C\d+)\b"
        if demonstration_profile
        else r"\b(?:[A-Z]{1,3}\d+[A-Z]?|T1)\b"
    )
    citation_slides = [index for index, content in enumerate(ocr_text, 1) if citation_pattern.search(content)]
    backstage_pattern = re.compile(
        r"\b(?:growth_opportunity|activation_implications|market_category_diagnosis|"
        r"growth_barriers|source_of_difference|evidence_and_uncertainty|artifact-|workflow_run|ev_)\b",
        re.IGNORECASE,
    )
    backstage_slides = [index for index, content in enumerate(ocr_text, 1) if backstage_pattern.search(content)]
    expected_copy_complete = all(
        isinstance(slide, dict)
        and all(
            str(slide.get(field) or "").strip().endswith((".", "?", "!"))
            and not backstage_pattern.search(str(slide.get(field) or ""))
            for field in ("body", "takeaway")
        )
        for slide in expected
    )
    copy_gaps = rendered_copy_gaps(expected, ocr_text, demonstration_profile=demonstration_profile)
    role_terms = {
        8: ("ownable space", "the gap", "committed dtc buyers", "fresh food competitors"),
        13: ("customer language", "paraphrased", "search shows", "reviews reveal", "social shows"),
        19: ("katkin future", "ownable territory"),
        22: ("role", "tension", "proof", "asset", "verbal assets", "tone motion", "recurring formats"),
    }
    if fieldwork_v4_profile:
        rendered_roles = all(
            slide_no <= len(ocr_text)
            and title in " ".join(normalized_words(ocr_text[slide_no - 1]))
            for slide_no, title in enumerate((
                "the commercial position today", "the 12 month opportunity",
                "where the gains come from", "the audience opportunity",
                "the strategic direction",
            ), 1)
        )
    elif demonstration_profile:
        rendered_roles = all(
            term in combined
            for term in (
                "the opportunity", "the constraint", "the advantage", "the strategy",
                "the creative future", "the growth engine", "the next 12 months",
            )
        )
    else:
        rendered_roles = all(
            slide_no <= len(ocr_text)
            and all(term in " ".join(normalized_words(ocr_text[slide_no - 1])) for term in terms)
            for slide_no, terms in role_terms.items()
        )

    receipt_path = args.slides_dir.parent / "render-receipt.json"
    receipt = load_object(receipt_path) if receipt_path.exists() else {}
    visual_manifest = receipt.get("visualManifest") or []
    image_relevance = True if fieldwork_v4_profile else (
        any(
            isinstance(item, dict) and item.get("role") == "creative illustration"
            for item in visual_manifest
        )
        and all(
            isinstance(item, dict)
            and bool(str(item.get("asset") or "").strip())
            and item.get("role") in {
                "brand subject", "scientific proof", "creative illustration"
            }
            and isinstance(item.get("slide"), int)
            for item in visual_manifest
        )
        if founder_quality_profile
        else not visual_manifest
        if demonstration_profile
        else bool(visual_manifest) and all(
            isinstance(item, dict)
            and bool(str(item.get("asset") or "").strip())
            and item.get("role") in {"brand subject", "scientific proof"}
            and isinstance(item.get("slide"), int)
            for item in visual_manifest
        )
    )

    rendered_source_register = bool(source_slides) and all(
        slide_no <= len(ocr_text)
        and (
            "evidence and assumptions ledger" in ocr_text[slide_no - 1].casefold()
            if demonstration_profile
            else "source register" in ocr_text[slide_no - 1].casefold()
        )
        for slide_no in source_slides
    )
    rendered_commercial_model = bool(model_slides) and all(
        slide_no <= len(ocr_text)
        and "revenue" in ocr_text[slide_no - 1].casefold()
        and (
            "conversion" in ocr_text[slide_no - 1].casefold()
            if demonstration_profile or fieldwork_v4_profile
            else "contribution" in ocr_text[slide_no - 1].casefold()
        )
        for slide_no in model_slides
    )

    checks = {
        "rendered_slide_count_matches_specification": len(slides) == len(expected) == len(ocr_text),
        "rendered_text_is_legible": len(ocr_text) == len(slides) and all(len(text.strip()) >= 24 for text in ocr_text),
        "rendered_slide_dimensions_are_complete": bool(expected_size)
        and expected_size[0] > expected_size[1]
        and all(size == expected_size for size in image_sizes),
        "rendered_copy_is_client_safe_and_complete": expected_copy_complete and not backstage_slides,
        "rendered_expected_copy_is_visible": not copy_gaps,
        (
            "rendered_seven_chapter_profile_is_complete"
            if demonstration_profile
            else "rendered_canonical_roles_are_substantive"
        ): rendered_roles,
        "no_rendered_truncation_markers": not truncated,
        "no_near_duplicate_rendered_layouts": not duplicate_pairs,
        "rendered_citations_are_visible": len(citation_slides) >= max(1, len(slides) - 2),
        "rendered_source_register_is_present": rendered_source_register,
        "rendered_commercial_model_is_present": rendered_commercial_model,
        "rendered_narrative_progression_is_complete": len(progression_hits) == len(progression_terms),
        "rendered_images_match_approved_roles": image_relevance,
    }
    findings = []
    if truncated:
        findings.append(f"truncation markers detected on rendered slides: {truncated}")
    if duplicate_pairs:
        findings.append(f"near-duplicate rendered layouts detected: {duplicate_pairs}")
    if backstage_slides:
        findings.append(f"backstage implementation labels detected on rendered slides: {backstage_slides}")
    if not expected_copy_complete:
        findings.append("presentation specification contains incomplete or backstage body/takeaway copy")
    if copy_gaps:
        findings.append(f"expected rendered copy is missing or clipped: {copy_gaps}")
    if not rendered_roles:
        findings.append(
            "rendered seven-chapter role checks failed"
            if demonstration_profile
            else "rendered canonical role checks failed for slides 8, 13, 19 or 22"
        )
    minimum_citation_slides = max(1, len(slides) - 2)
    if len(citation_slides) < minimum_citation_slides:
        findings.append(
            "readable citations detected on "
            f"{len(citation_slides)} of {len(slides)} slides; expected at least {minimum_citation_slides}"
        )
    missing_progression = sorted(set(progression_terms) - set(progression_hits))
    if missing_progression:
        findings.append(f"rendered narrative stages not visible: {missing_progression}")
    report = {
        "status": "passed" if all(checks.values()) else "failed",
        "review_basis": "rendered_png_pixels_and_macos_vision_ocr",
        "checks": checks,
        "findings": findings,
        "duplicate_layout_pairs": duplicate_pairs,
        "truncated_slides": truncated,
        "rendered_copy_gaps": copy_gaps,
        "rendered_slide_dimensions": [list(size) for size in image_sizes],
        "citation_slides": citation_slides,
        "progression_terms_found": progression_hits,
        "ocr_output": str(ocr_path),
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
