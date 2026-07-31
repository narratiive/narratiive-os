import unittest

from runtime.mission_control_domains import REQUIRED_MISSION_CONTROL_DOMAINS
from runtime.mission_control_gateway_loader import MissionControlGatewayLoader


class StubSnapshot:
    def __init__(self, payload):
        self.payload = payload

    def to_dict(self):
        return self.payload


class MissionControlGatewayLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot_calls = []
        self.domain_calls = []

        def load_snapshot(workspace_id):
            self.snapshot_calls.append(workspace_id)
            return StubSnapshot(
                {
                    "generated_at": "2026-07-31T12:00:00Z",
                    "status": "partial",
                    "recommended_focus_details": [
                        {
                            "action": "advance:mission-control:connect public gateway",
                            "category": "workstream",
                            "confidence": "high",
                            "evidence": ["workstreams/0"],
                        }
                    ],
                }
            )

        def load_domains(workspace_id):
            self.domain_calls.append(workspace_id)
            return {
                "health": {
                    "state": "connected",
                    "evidence": ["progress/status"],
                },
                "active_work": {
                    "state": "connected",
                    "evidence": ["workstreams/0"],
                },
            }

        self.loader = MissionControlGatewayLoader(
            workspace_id="narratiive",
            snapshot_loader=load_snapshot,
            domain_values_loader=load_domains,
        )

    def test_builds_canonical_public_snapshot_for_gateway(self) -> None:
        payload = self.loader("narratiive").to_dict()

        self.assertEqual(payload["workspace_id"], "narratiive")
        self.assertEqual(payload["snapshot"]["status"], "partial")
        self.assertEqual(tuple(payload["domains"]), REQUIRED_MISSION_CONTROL_DOMAINS)
        self.assertEqual(payload["domains"]["health"]["state"], "connected")
        self.assertEqual(payload["domains"]["publishing"]["state"], "not_connected")
        self.assertEqual(self.snapshot_calls, ["narratiive"])
        self.assertEqual(self.domain_calls, ["narratiive"])

    def test_cross_workspace_request_fails_before_loading_sources(self) -> None:
        with self.assertRaisesRegex(ValueError, "workspace mismatch"):
            self.loader("client-a")

        self.assertEqual(self.snapshot_calls, [])
        self.assertEqual(self.domain_calls, [])

    def test_invalid_domain_payload_fails_closed(self) -> None:
        loader = MissionControlGatewayLoader(
            workspace_id="narratiive",
            snapshot_loader=lambda _: StubSnapshot({"status": "healthy"}),
            domain_values_loader=lambda _: ["not", "an", "object"],
        )

        with self.assertRaisesRegex(TypeError, "domain values must be an object"):
            loader("narratiive")

    def test_output_is_deterministic_for_same_source_state(self) -> None:
        first = self.loader("narratiive").to_dict()
        second = self.loader("narratiive").to_dict()

        self.assertEqual(first, second)

    def test_missing_domain_integrations_remain_explicit(self) -> None:
        loader = MissionControlGatewayLoader(
            workspace_id="narratiive",
            snapshot_loader=lambda _: StubSnapshot({"status": "partial"}),
            domain_values_loader=lambda _: None,
        )

        payload = loader("narratiive").to_dict()
        self.assertTrue(
            all(domain["state"] == "not_connected" for domain in payload["domains"].values())
        )


if __name__ == "__main__":
    unittest.main()
