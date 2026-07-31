import unittest

from runtime.mission_control_read_action import MissionControlReadAction


class StubSnapshot:
    def __init__(self, payload):
        self.payload = payload

    def to_dict(self):
        return self.payload


class MissionControlReadActionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls = []

        def load_snapshot(workspace_id):
            self.calls.append(workspace_id)
            return StubSnapshot(
                {
                    "workspace_id": workspace_id,
                    "snapshot": {"status": "partial"},
                    "domains": {
                        "health": {
                            "state": "connected",
                            "evidence": ["progress/status"],
                        },
                        "publishing": {
                            "state": "not_connected",
                            "evidence": [],
                        },
                    },
                }
            )

        self.action = MissionControlReadAction(
            workspace_id="narratiive",
            snapshot_loader=load_snapshot,
        )

    def test_returns_canonical_read_only_snapshot(self) -> None:
        response = self.action.execute(
            {"action": "mission_control_snapshot", "workspace_id": "narratiive"}
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["action"], "mission_control_snapshot")
        self.assertEqual(response["workspace_id"], "narratiive")
        self.assertEqual(response["data"]["snapshot"]["status"], "partial")
        self.assertEqual(
            response["data"]["domains"]["publishing"]["state"],
            "not_connected",
        )
        self.assertEqual(self.calls, ["narratiive"])

    def test_cross_workspace_request_fails_before_loading_snapshot(self) -> None:
        with self.assertRaisesRegex(ValueError, "workspace mismatch"):
            self.action.execute(
                {"action": "mission_control_snapshot", "workspace_id": "client-a"}
            )

        self.assertEqual(self.calls, [])

    def test_mutating_payload_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not accept payload"):
            self.action.execute(
                {
                    "action": "mission_control_snapshot",
                    "workspace_id": "narratiive",
                    "payload": {"status": "healthy"},
                }
            )

        self.assertEqual(self.calls, [])

    def test_unsupported_action_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported action"):
            self.action.execute(
                {"action": "update_mission_control", "workspace_id": "narratiive"}
            )

    def test_invalid_snapshot_fails_closed(self) -> None:
        action = MissionControlReadAction(
            workspace_id="narratiive",
            snapshot_loader=lambda _: StubSnapshot(
                {"workspace_id": "client-a", "snapshot": {}, "domains": {}}
            ),
        )

        with self.assertRaisesRegex(ValueError, "snapshot workspace mismatch"):
            action.execute(
                {"action": "mission_control_snapshot", "workspace_id": "narratiive"}
            )

    def test_output_is_deterministic_for_same_snapshot(self) -> None:
        request = {"action": "mission_control_snapshot", "workspace_id": "narratiive"}

        self.assertEqual(self.action.execute(request), self.action.execute(request))


if __name__ == "__main__":
    unittest.main()
