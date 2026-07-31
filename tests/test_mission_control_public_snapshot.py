import json
import unittest

from runtime.mission_control_domains import REQUIRED_MISSION_CONTROL_DOMAINS
from runtime.mission_control_public_snapshot import MissionControlPublicSnapshotBuilder


class StubSnapshot:
    def __init__(self, payload):
        self.payload = payload

    def to_dict(self):
        return self.payload


class MissionControlPublicSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = MissionControlPublicSnapshotBuilder(workspace_id="narratiive")

    def test_builds_workspace_scoped_snapshot_with_every_canonical_domain(self) -> None:
        public = self.builder.build(
            requested_workspace_id="narratiive",
            snapshot=StubSnapshot(
                {
                    "generated_at": "2026-07-31T11:00:00Z",
                    "status": "partial",
                    "recommended_focus_details": [],
                }
            ),
            domain_values={
                "active_work": {
                    "state": "connected",
                    "evidence": ["workstreams/0"],
                },
                "approvals": {
                    "state": "connected",
                    "evidence": ["approvals_required/0"],
                },
            },
        )

        payload = public.to_dict()
        self.assertEqual(payload["workspace_id"], "narratiive")
        self.assertEqual(payload["snapshot"]["status"], "partial")
        self.assertEqual(tuple(payload["domains"]), REQUIRED_MISSION_CONTROL_DOMAINS)
        self.assertEqual(payload["domains"]["active_work"]["state"], "connected")
        self.assertEqual(payload["domains"]["publishing"]["state"], "not_connected")

    def test_output_is_deterministic_for_the_same_source_state(self) -> None:
        source = StubSnapshot({"generated_at": "2026-07-31T11:00:00Z", "status": "healthy"})
        domains = {
            "health": {"state": "connected", "evidence": ["progress/status"]},
            "recent_wins": {"state": "connected", "evidence": ["recent_wins/0"]},
        }

        first = self.builder.build(
            requested_workspace_id="narratiive",
            snapshot=source,
            domain_values=domains,
        ).to_dict()
        second = self.builder.build(
            requested_workspace_id="narratiive",
            snapshot=source,
            domain_values=domains,
        ).to_dict()

        self.assertEqual(first, second)

    def test_snapshot_isolated_from_source_mutation(self) -> None:
        source_payload = {
            "status": "partial",
            "recommended_focus_details": [{"recommendation": "Review approvals"}],
        }
        public = self.builder.build(
            requested_workspace_id="narratiive",
            snapshot=StubSnapshot(source_payload),
        )

        source_payload["status"] = "healthy"
        source_payload["recommended_focus_details"][0]["recommendation"] = "Changed"

        payload = public.to_dict()
        self.assertEqual(payload["snapshot"]["status"], "partial")
        self.assertEqual(
            payload["snapshot"]["recommended_focus_details"][0]["recommendation"],
            "Review approvals",
        )

    def test_serialized_payload_mutation_does_not_change_snapshot(self) -> None:
        public = self.builder.build(
            requested_workspace_id="narratiive",
            snapshot=StubSnapshot(
                {
                    "status": "partial",
                    "recommended_focus_details": [{"recommendation": "Review approvals"}],
                }
            ),
        )

        first = public.to_dict()
        first["snapshot"]["status"] = "healthy"
        first["snapshot"]["recommended_focus_details"][0]["recommendation"] = "Changed"

        second = public.to_dict()
        self.assertEqual(second["snapshot"]["status"], "partial")
        self.assertEqual(
            second["snapshot"]["recommended_focus_details"][0]["recommendation"],
            "Review approvals",
        )

    def test_non_serializable_nested_value_fails_closed(self) -> None:
        with self.assertRaisesRegex(TypeError, "serializable values"):
            self.builder.build(
                requested_workspace_id="narratiive",
                snapshot=StubSnapshot({"status": object()}),
            )

    def test_non_finite_numbers_fail_closed(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "finite numeric values"):
                    self.builder.build(
                        requested_workspace_id="narratiive",
                        snapshot=StubSnapshot({"confidence": value}),
                    )

    def test_snapshot_is_strict_json_serializable(self) -> None:
        public = self.builder.build(
            requested_workspace_id="narratiive",
            snapshot=StubSnapshot({"confidence": 0.8, "status": "healthy"}),
        )

        encoded = json.dumps(public.to_dict(), allow_nan=False, sort_keys=True)

        self.assertIn('"confidence": 0.8', encoded)

    def test_cross_workspace_snapshot_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "workspace mismatch"):
            self.builder.build(
                requested_workspace_id="client-a",
                snapshot=StubSnapshot({"status": "healthy"}),
            )

    def test_non_object_snapshot_fails_closed(self) -> None:
        with self.assertRaisesRegex(TypeError, "snapshot must serialize to an object"):
            self.builder.build(
                requested_workspace_id="narratiive",
                snapshot=StubSnapshot(["not", "an", "object"]),
            )

    def test_invalid_domain_evidence_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "connected Mission Control domains require evidence"):
            self.builder.build(
                requested_workspace_id="narratiive",
                snapshot=StubSnapshot({"status": "healthy"}),
                domain_values={"health": {"state": "connected"}},
            )


if __name__ == "__main__":
    unittest.main()
