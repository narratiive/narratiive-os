from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from runtime.sketchbook_v2 import PAGE_TYPES, SketchbookV2Worker, validate_sketchbook_v2


def sample(client_id="katkin"):
    manifest = {"client_id": client_id, "version": "1", "palette": {k: "#111111" for k in ("ink","paper","accent","secondary","muted","rule","white")}, "display_typeface": "Arial", "body_typeface": "Arial", "imagery_rules": ["client-specific"], "product_rules": ["no claims"], "rights_and_provenance": ["generated illustration"]}
    pages=[]
    values={
      "creative_proposition":{"proposition_line_1":"DECIDE WITH","proposition_line_2":"EVIDENCE","emotional_payoff":"Confidence at the feeding decision.","commercial_role":"support transition","hero_image":"hero.png"},
      "audience_profile":{"audience_name":"The careful switcher","human_truth":"Wants confidence, not another claim.","wants":"Useful proof","hesitates":"Price and routine","moves_when":"The next step is clear","validation_status":"hypothesis","portrait":"hero.png","creative_job":"make change feel manageable"},
      "visual_world":{"art_direction_statement":"PROGRESS, MADE VISIBLE.","hero_reference":"hero.png","setting_rule":"real routines","legibility_rule":"one signal","avoid_list":["clinical theatre"]},
      "campaign_territory":{"territory_name":"THE DECISION SYSTEM","territory_role":"Turn evidence into a useful next step.","hero_copy":"WHAT DO WE KNOW? WHAT DO WE DO NEXT?","repeatable_construction":["decision","evidence","action"],"evidence_label":"illustrative concept","hero_execution":"native type","commercial_objective":"support trial-to-subscription"},
      "campaign_executions":{"applications":[{"channel":"CRM"},{"channel":"OWNED"},{"channel":"RETAIL"}],"activation_status":"illustrative_not_live"}}
    for kind in PAGE_TYPES: pages.append({"type":kind,**values[kind]})
    return {"contract_version":"2.0.0","fieldwork_handoff":{"artifact_id":"fw-1","checksum":"abc","approval_status":"approved"},"client_manifest":manifest,"pages":pages}


class SketchbookV2Tests(unittest.TestCase):
    def test_accepts_five_page_client_contract(self): self.assertEqual(len(validate_sketchbook_v2(sample())["pages"]),5)
    def test_rejects_unapproved_fieldwork(self):
        value=sample(); value["fieldwork_handoff"]["approval_status"]="pending"
        with self.assertRaisesRegex(ValueError,"approved FIELDWORK"): validate_sketchbook_v2(value)
    def test_rejects_rave_leakage(self):
        value=sample(); value["pages"][3]["territory_name"]="The Anti-Snob"
        with self.assertRaisesRegex(ValueError,"Rave"): validate_sketchbook_v2(value)
    def test_worker_stops_at_human_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            def render(spec,out):
                out.mkdir(parents=True); (out/"x.pptx").write_bytes(b"x"); (out/"x.pdf").write_bytes(b"x")
                return {"pptx":out/"x.pptx","pdf":out/"x.pdf","visual_qa_status":"passed","visual_qa":{"pages":5}}
            worker=SketchbookV2Worker(render,lambda p,s:{"presentation_url":"https://docs.google.com/presentation/d/1","presentation_id":"1"},Path(tmp))
            result=worker(sample()); self.assertFalse(result["client_release_authorised"])

if __name__ == "__main__": unittest.main()
