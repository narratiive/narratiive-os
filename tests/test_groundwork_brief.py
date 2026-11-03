"""One focused contract/render verification, with synthetic evidence only."""
import copy
import hashlib
import json
import tempfile
import unittest
from pypdf import PdfReader
from runtime.groundwork import WEIGHTS, qualification, validate_prospect_intelligence
from runtime.human_review_artifacts import HumanReviewArtifactStore, HumanReviewPresentationService, HumanReviewArtifactError
from runtime.models import WorkflowState, ArtifactRef
from runtime.workflow_instructions import workflow_instruction
from runtime.tony_blueprint_lite_inbound import TonyInboundBlueprintLiteService
from runtime.workflow_registry import GROWTH_DIAGNOSTIC_TO_BLUEPRINT_LITE


def synthetic_brief():
    return {
        "assessed_on": "2026-11-03", "verdict": "Qualify the synthetic company's mandate before pursuing a pitch.",
        "confidence": "Low - synthetic public-source fixture, no buying evidence.",
        "scorecard": [{"criterion": k, "score": w - 5, "rationale": "Interpretation: synthetic channel evidence [1] suggests potential; budget and mandate remain unknown."} for k, w in WEIGHTS.items()],
        "company_and_people": "Synthetic company trades through wholesale and ecommerce [1]. Founder background is unknown.",
        "brand_character": "Interpretation: the synthetic copy is restrained and craft-led [1]; creative compatibility requires validation.",
        "marketing_examples": ["Synthetic subscription offer supports a repeat-purchase hypothesis [1].", "Synthetic collaboration offers a partner acquisition hypothesis [2]."],
        "channel_limits": "Paid advertising and social cadence were not verified. Internal performance is unknown.",
        "growth_hypotheses": ["Hypothesis: onboarding could support repeat purchase [1]; validate retention.", "Hypothesis: partnerships could acquire customers [2]; validate incrementality."],
        "discovery_questions": ["What is the funded growth priority?", "Which cohorts retain profitably?", "Who owns the agency brief?"],
        "unknowns": "Budget, mandate and performance are unknown. Agency fit is an assumption.",
        "sources": [{"label": f"Synthetic source {n}", "url": f"https://example.com/{n}", "checked_on": "2026-11-03"} for n in range(1, 4)],
    }


class GroundworkBriefTest(unittest.TestCase):
    def test_generation_contract_and_bounded_immutable_pdf(self):
        brief = synthetic_brief()
        self.assertEqual(validate_prospect_intelligence(brief), [])
        self.assertEqual(qualification(brief), (80, "Priority prospect", "PURSUE"))
        for total, expected in ((79, "QUALIFY"), (70, "QUALIFY"), (69, "DEPRIORITISE")):
            candidate = copy.deepcopy(brief)
            candidate["scorecard"][0]["score"] -= 80 - total
            self.assertEqual(qualification(candidate)[2], expected)
        bad = copy.deepcopy(brief)
        bad["scorecard"][0]["score"] = 31
        self.assertTrue(validate_prospect_intelligence(bad))
        bad = copy.deepcopy(brief)
        bad["scorecard"][0]["rationale"] = {"unexpected": "uncited claim"}
        self.assertTrue(validate_prospect_intelligence(bad))
        bad = copy.deepcopy(brief)
        bad["sources"][0]["url"] = "javascript:alert(1)"
        self.assertTrue(validate_prospect_intelligence(bad))
        self.assertNotIn("prospect_intelligence", GROWTH_DIAGNOSTIC_TO_BLUEPRINT_LITE.stages[0].output_contract.required_fields)
        self.assertIn("prospect_intelligence", workflow_instruction("growth_diagnostic_to_blueprint_lite", "prepare_blueprint_lite", ()))
        from runtime.inbound_leads import InboundLead
        # Both commission paths share the same compact contract.
        self.assertIn("prospect_intelligence", TonyInboundBlueprintLiteService._instruction(InboundLead.from_mapping({"lead_id": "safe", "company": "Synthetic", "contact": "Synthetic", "email": "safe@example.com"})))
        for url in ("https://[invalid", "javascript:alert(1)"):
            bad = copy.deepcopy(brief)
            bad["sources"][0]["url"] = url
            self.assertTrue(validate_prospect_intelligence(bad))
        bad = copy.deepcopy(brief)
        bad["sources"][0]["label"] = {"unexpected": "object"}
        self.assertTrue(validate_prospect_intelligence(bad))
        bad = copy.deepcopy(brief)
        bad["marketing_examples"][0] += " Unbacked claim [9]."
        self.assertTrue(validate_prospect_intelligence(bad))
        self.assertTrue(validate_prospect_intelligence(brief, verified_sources=[]))
        with tempfile.TemporaryDirectory() as directory:
            state = WorkflowState(workflow_id="growth_diagnostic_to_blueprint_lite", run_id="groundwork-review-test", stages=[], workspace_id="qualification-test", client_id="synthetic-review", entity_id="synthetic-review", input_payload={"company": "Synthetic Review Company"})
            service = HumanReviewPresentationService(HumanReviewArtifactStore(directory))
            output = {"prospect_intelligence": brief, "source_backed_evidence": [{"uri": x["url"]} for x in brief["sources"]]}
            source = ArtifactRef(artifact_id="synthetic-groundwork", artifact_type="blueprint_lite", location="synthetic.json", checksum=hashlib.sha256(json.dumps(output).encode()).hexdigest())
            result = service.produce(state=state, source=source, output=output)
            reader = PdfReader(result.location)
            self.assertLessEqual(len(reader.pages), 2)
            text = "\n".join(p.extract_text() for p in reader.pages)
            for expected in ("Prospect Intelligence Brief", "80/100", "SOURCES", "PRIORITY DISCOVERY QUESTIONS"):
                self.assertIn(expected, text)
            self.assertEqual(service.produce(state=state, source=source, output=output), result)
            overflow = copy.deepcopy(output)
            overflow["prospect_intelligence"]["company_and_people"] = "Long substantive observation. " * 1500
            with self.assertRaises(HumanReviewArtifactError):
                service.produce(state=state, source=source, output=overflow)

if __name__ == "__main__":
    unittest.main()
