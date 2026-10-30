from __future__ import annotations

import hashlib
import json
import unittest

from runtime.campaign_production_planning_worker import (
    CampaignProductionPlanningError,
    CampaignProductionPlanningWorker,
)
from runtime.worker_registry import (
    CapabilityWorkerRegistry,
    WorkerAvailability,
    WorkerMetadata,
    WorkerRegistration,
    WorkerSelectionPolicy,
)
from runtime.workflow_quality import production_planning_quality_gate
from tests.test_workflow_quality import campaign_identity, creative_bible_output


def planning_contract() -> dict:
    bible = creative_bible_output()["creative_directors_bible"]
    checksum = hashlib.sha256(
        json.dumps(bible, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return {
        "campaign_identity": campaign_identity(),
        "approved_creative_bible": bible,
        "creative_bible_approval": {
            "decision": "creative_bible_approval",
            "approver": "telegram:matt",
            "rationale": "Approved exact version.",
            "creative_bible_checksum": checksum,
        },
        "production_constraints": ["No publication", "Human review required"],
        "workflow_context": {"workflow_id": "creative_bible_to_asset_production"},
    }


class CampaignProductionPlanningWorkerTests(unittest.TestCase):
    def test_approved_bible_generates_versioned_non_executing_production_pack(self) -> None:
        result = CampaignProductionPlanningWorker()(planning_contract())

        self.assertEqual(len(result["channel_asset_specifications"]), 18)
        self.assertEqual(len(result["production_tasks"]), 18)
        self.assertEqual(len(result["asset_manifest"]["assets"]), 18)
        self.assertTrue(all(task["human_review_required"] for task in result["production_tasks"]))
        self.assertTrue(all(not task["execution_authorised"] for task in result["production_tasks"]))
        self.assertFalse(result["production_executed"])
        self.assertFalse(result["publication_authorised"])
        self.assertFalse(result["media_spend_authorised"])
        self.assertTrue(production_planning_quality_gate(result)["passed"])

    def test_stale_bible_approval_is_rejected_before_planning(self) -> None:
        contract = planning_contract()
        contract["creative_bible_approval"]["creative_bible_checksum"] = "0" * 64

        with self.assertRaisesRegex(CampaignProductionPlanningError, "checksum"):
            CampaignProductionPlanningWorker()(contract)

    def test_without_a_registry_every_task_stays_unrouted(self) -> None:
        result = CampaignProductionPlanningWorker()(planning_contract())

        self.assertTrue(all(task["route_status"] == "unrouted" for task in result["production_tasks"]))
        self.assertTrue(all(task["worker_id"] == "" for task in result["production_tasks"]))
        self.assertTrue(production_planning_quality_gate(result)["passed"])

    def test_registered_capability_routes_its_tasks_to_the_eligible_worker(self) -> None:
        registry = CapabilityWorkerRegistry(
            [
                WorkerRegistration(
                    metadata=WorkerMetadata(
                        worker_id="image-worker-1",
                        provider="Narratiive Image Studio",
                        capabilities=("image_generation",),
                        availability=WorkerAvailability.AVAILABLE,
                    ),
                    adapter=lambda payload: payload,
                )
            ]
        )
        worker = CampaignProductionPlanningWorker(registry=registry)

        result = worker(planning_contract())
        tasks = result["production_tasks"]
        routed = [task for task in tasks if task["required_capability"] == "image_generation"]
        unrouted = [task for task in tasks if task["required_capability"] != "image_generation"]

        self.assertTrue(routed, "fixture must include at least one image_generation task")
        self.assertTrue(all(task["route_status"] == "routed" for task in routed))
        self.assertTrue(all(task["worker_id"] == "image-worker-1" for task in routed))
        self.assertTrue(all(task["provider"] == "Narratiive Image Studio" for task in routed))
        self.assertTrue(all(task["execution_authorised"] is False for task in routed))
        self.assertTrue(unrouted, "fixture must include at least one task needing a different capability")
        self.assertTrue(all(task["route_status"] == "unavailable" for task in unrouted))
        self.assertTrue(all(task["worker_id"] == "" for task in unrouted))
        self.assertTrue(production_planning_quality_gate(result)["passed"])

    def test_configured_registry_does_not_grant_execution_or_spend_authority(self) -> None:
        registry = CapabilityWorkerRegistry(
            [
                WorkerRegistration(
                    metadata=WorkerMetadata(
                        worker_id="image-worker-1",
                        provider="Narratiive Image Studio",
                        capabilities=("image_generation", "short_form_video_production", "audio_production", "layout_design"),
                        availability=WorkerAvailability.AVAILABLE,
                    ),
                    adapter=lambda payload: payload,
                )
            ]
        )
        worker = CampaignProductionPlanningWorker(registry=registry, policy=WorkerSelectionPolicy(policy_id="test-policy"))

        result = worker(planning_contract())

        self.assertTrue(all(task["route_status"] == "routed" for task in result["production_tasks"]))
        self.assertTrue(all(task["policy_id"] == "test-policy" for task in result["production_tasks"]))
        self.assertFalse(result["production_executed"])
        self.assertFalse(result["publication_authorised"])
        self.assertFalse(result["media_spend_authorised"])
        self.assertTrue(all(not task["execution_authorised"] for task in result["production_tasks"]))
        self.assertTrue(production_planning_quality_gate(result)["passed"])


if __name__ == "__main__":
    unittest.main()
