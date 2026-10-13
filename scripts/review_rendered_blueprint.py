#!/usr/bin/env python3
"""Review rendered slide pixels and OCR output before a Blueprint can pass QA."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


def load_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def layout_signature(path: Path) -> np.ndarray:
    image = Image.open(path).convert("L").resize((64, 36))
    edges = image.filter(ImageFilter.FIND_EDGES)
    matrix = np.asarray(edges, dtype=np.float64)
    matrix[:7, :] = 0
    matrix[-5:, :] = 0
    vector = matrix.reshape(-1)
    norm = np.linalg.norm(vector)
    return vector / norm if norm else vector


def similarity(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.dot(left, right))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("slides_dir", type=Path)
    parser.add_argument("specification", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--swift", default="/usr/bin/swift")
    parser.add_argument("--ocr-script", type=Path, required=True)
    args = parser.parse_args()

    spec = load_object(args.specification)
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

    progression_terms = ("constraint", "proof", "audience", "position", "commercial", "creative", "source", "mandate")
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
    citation_pattern = re.compile(r"\b(?:S\d+[A-Z]?|T1)\b")
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
    role_terms = {
        8: ("ownable space", "the gap"),
        13: ("customer says", "search shows", "reviews reveal", "social shows"),
        19: ("katkin future", "ownable territory"),
        22: ("role", "tension", "proof", "asset"),
    }
    rendered_roles = all(
        slide_no <= len(ocr_text)
        and all(term in ocr_text[slide_no - 1].casefold() for term in terms)
        for slide_no, terms in role_terms.items()
    )

    receipt_path = args.slides_dir.parent / "render-receipt.json"
    receipt = load_object(receipt_path) if receipt_path.exists() else {}
    visual_manifest = receipt.get("visualManifest") or []
    image_relevance = bool(visual_manifest) and all(
        isinstance(item, dict)
        and bool(str(item.get("asset") or "").strip())
        and item.get("role") in {"brand subject", "scientific proof"}
        and isinstance(item.get("slide"), int)
        for item in visual_manifest
    )

    checks = {
        "rendered_slide_count_matches_specification": len(slides) == len(expected) == len(ocr_text),
        "rendered_text_is_legible": len(ocr_text) == len(slides) and all(len(text.strip()) >= 24 for text in ocr_text),
        "rendered_copy_is_client_safe_and_complete": expected_copy_complete and not backstage_slides,
        "rendered_canonical_roles_are_substantive": rendered_roles,
        "no_rendered_truncation_markers": not truncated,
        "no_near_duplicate_rendered_layouts": not duplicate_pairs,
        "rendered_citations_are_visible": len(citation_slides) >= max(1, len(slides) - 2),
        "rendered_source_register_is_present": bool(source_slides) and all(
            slide_no <= len(ocr_text) and "source register" in ocr_text[slide_no - 1].casefold()
            for slide_no in source_slides
        ),
        "rendered_commercial_model_is_present": bool(model_slides) and all(
            slide_no <= len(ocr_text)
            and "revenue" in ocr_text[slide_no - 1].casefold()
            and "contribution" in ocr_text[slide_no - 1].casefold()
            for slide_no in model_slides
        ),
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
    if not rendered_roles:
        findings.append("rendered canonical role checks failed for slides 8, 13, 19 or 22")
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
        "citation_slides": citation_slides,
        "progression_terms_found": progression_hits,
        "ocr_output": str(ocr_path),
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
