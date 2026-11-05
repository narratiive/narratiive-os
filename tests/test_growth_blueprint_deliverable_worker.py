from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.deliverable_production import FakePresentationRenderer, FileDeliverableStore, _checksum
from runtime.growth_blueprint_deliverable_worker import (
    GrowthBlueprintDeliverableWorker,
    GrowthBlueprintDeliverableWorkerError,
    build_growth_blueprint_deliverable_worker,
)
from runtime.workflow_quality import growth_blueprint_deliverable_quality_gate
from tests.test_deliverable_production import artifact, commercial_intelligence, source_register


class CountingRenderer(FakePresentationRenderer):
    def __init__(self) -> None:
        self.calls = 0

    def render(self, specification, output_dir):
        self.calls += 1
        return super().render(specification, output_dir)


def contract(source: dict, *, checksum: str | None = None) -> dict:
    return {
        "quality_accepted_growth_blueprint": source,
        "blueprint_identity": {
            "artifact_id": "artifact-northstar-approved-v1",
            "version": 1,
            "checksum": checksum or _checksum(source),
        },
        "client_context": {"name": "Northstar Test Co"},
        "commercial_intelligence": commercial_intelligence(),
        "source_register": source_register(),
        "workflow_context": {
            "workflow_id": "growth_blueprint_deliverable_production",
            "stage_id": "produce_growth_blueprint_deliverable",
            "workspace_id": "northstar-test-workspace",
            "client_id": "northstar-test-co",
            "run_id": "northstar-test-blueprint-deliverable-v1",
        },
    }


class GrowthBlueprintDeliverableWorkerTests(unittest.TestCase):
    def test_produces_review_only_deliverable_and_replays_without_rerendering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            renderer = CountingRenderer()
            worker = GrowthBlueprintDeliverableWorker(
                renderer=renderer,
                store=FileDeliverableStore(root / "records"),
                output_root=root / "outputs",
            )
            source = artifact()

            first = worker(contract(source))
            replay = worker(contract(source))

            self.assertTrue(growth_blueprint_deliverable_quality_gate(first)["passed"])
            self.assertFalse(first["external_action_taken"])
            self.assertFalse(first["publication_authorised"])
            self.assertFalse(first["delivery_authorised"])
            self.assertFalse(first["replay"])
            self.assertTrue(replay["replay"])
            self.assertEqual(renderer.calls, 1)
            self.assertTrue(Path(first["editable_pptx"]).is_file())
            self.assertTrue(Path(first["review_pdf"]).is_file())
            self.assertEqual(len(first["commercial_model"]["scenarios"]), 3)
            self.assertTrue(first["source_register"]["entries"])
            self.assertFalse(first["execution_evidence"]["codex_dependency"])
            self.assertEqual(first["execution_evidence"]["provider_calls"], 0)

    def test_rejects_blueprint_whose_content_no_longer_matches_approved_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            worker = GrowthBlueprintDeliverableWorker(
                renderer=FakePresentationRenderer(),
                store=FileDeliverableStore(root / "records"),
                output_root=root / "outputs",
            )
            with self.assertRaisesRegex(GrowthBlueprintDeliverableWorkerError, "checksum"):
                worker(contract(artifact(), checksum="0" * 64))

    def test_client_scopes_do_not_share_deliverable_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            renderer = CountingRenderer()
            worker = GrowthBlueprintDeliverableWorker(
                renderer=renderer,
                store=FileDeliverableStore(root / "records"),
                output_root=root / "outputs",
            )
            source = artifact()
            first = contract(source)
            second = contract(source)
            second["workflow_context"] = {
                **second["workflow_context"],
                "client_id": "northstar-test-co-two",
                "run_id": "northstar-test-blueprint-deliverable-v2",
            }

            worker(first)
            worker(second)

            self.assertEqual(renderer.calls, 2)

    def test_factory_is_disabled_by_default_and_fails_closed_when_misconfigured(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertIsNone(build_growth_blueprint_deliverable_worker(temporary, {}))
            with self.assertRaisesRegex(GrowthBlueprintDeliverableWorkerError, "paths are unavailable"):
                build_growth_blueprint_deliverable_worker(
                    temporary,
                    {"NARRATIIVE_DOCUMENT_WORKER_MODE": "local_artifact_tool"},
                )


if __name__ == "__main__":
    unittest.main()

class BlueprintDirectorProductionWiringTests(unittest.TestCase):
    def test_director_only_source_renders_without_legacy_sections_or_rewriting_story(self):
        pages=[{'page_number':i,'act':'The proposed strategy','headline':f'Specific strategic conclusion {i}',
            'body':f'Evidence-led reasoning for the distinct decision on page {i}. This is a synthetic contract fixture, not a company fact.',
            'commercial_consequence':'A bounded decision that requires validation before activation.',
            'visual_opportunity':'One clear editorial argument per page.','visual_archetype':'audience_reality_split' if i == 4 else 'single_thesis_page'} for i in range(1,13)]
        source={'client_facing_blueprint':{'title':'SAFE Director strategy','pages':pages},
            'editorial_trace':[{'page_number':i,'evidence_refs':['ev-audience']} for i in range(1,13)]}
        intelligence={'mechanism':'incremental_accounts_year_one','inputs':[
            {'input_id':'annual_account_revenue','label':'Assumed annual account revenue','value':22000,'unit':'GBP','source_ids':['S1'],'status':'assumption'}],
            'scenario_assumptions':[{'name':n,'additional_accounts':a,'year_one_ramp':r} for n,a,r in [('Conservative',8,.35),('Base',12,.45),('Upside',16,.55)]],
            'implementation_cost':{'status':'unavailable','value':None}}
        with tempfile.TemporaryDirectory() as tmp:
            worker=GrowthBlueprintDeliverableWorker(renderer=CountingRenderer(),store=FileDeliverableStore(Path(tmp)/'records'),output_root=Path(tmp)/'outputs')
            request=contract(source);request['commercial_intelligence']=intelligence
            result=worker(request)
            slides=result['presentation_specification']['slides']
            original=[s for s in slides if s['title'].startswith('Specific strategic conclusion')]
            self.assertEqual([s['title'] for s in original],[p['headline'] for p in pages])
            self.assertEqual(len(slides),15)
            self.assertEqual(original[3]['layout_type'], 'audience_reality_split')
            register_slide = next(s for s in slides if s['layout_type'] == 'source_register')
            self.assertEqual(register_slide['content_data']['entries'], result['source_register']['entries'])
            self.assertTrue(all(e['applies_to_pages'] for e in register_slide['content_data']['entries']))
            self.assertEqual(result['commercial_model']['scenarios'][1]['incremental_annual_revenue'],118800)
            self.assertTrue(growth_blueprint_deliverable_quality_gate(result)['passed'], growth_blueprint_deliverable_quality_gate(result))
            self.assertNotIn('full_blueprint_has_exactly_thirty_slides',growth_blueprint_deliverable_quality_gate(result)['checks'])
            self.assertFalse(result['delivery_authorised'])

    def test_account_model_missing_profit_is_only_accepted_when_explicitly_unknown(self):
        source = artifact()
        with tempfile.TemporaryDirectory() as tmp:
            worker = GrowthBlueprintDeliverableWorker(renderer=CountingRenderer(), store=FileDeliverableStore(Path(tmp)/'records'), output_root=Path(tmp)/'outputs')
            result = worker(contract(source))
            result['commercial_model']['scenarios'][0]['incremental_annual_contribution'] = None
            self.assertFalse(growth_blueprint_deliverable_quality_gate(result)['passed'])
