import unittest

from runtime.mission_control_domains import (
    MissionControlDomainRegistry,
    MissionControlDomainStatus,
    REQUIRED_MISSION_CONTROL_DOMAINS,
)


class MissionControlDomainRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = MissionControlDomainRegistry()

    def test_missing_domains_are_explicitly_not_connected(self):
        statuses = self.registry.resolve()

        self.assertEqual(
            tuple(item.domain for item in statuses),
            REQUIRED_MISSION_CONTROL_DOMAINS,
        )
        self.assertTrue(all(item.state == "not_connected" for item in statuses))
        self.assertTrue(all(item.evidence == () for item in statuses))

    def test_connected_and_degraded_domains_preserve_evidence(self):
        statuses = self.registry.to_dict(
            {
                "health": {
                    "state": "connected",
                    "evidence": ["runtime:healthy", "runtime:healthy"],
                },
                "commercial_pipeline": {
                    "state": "degraded",
                    "evidence": "notion:permission_required",
                },
            }
        )

        self.assertEqual(statuses["health"]["evidence"], ["runtime:healthy"])
        self.assertEqual(statuses["commercial_pipeline"]["state"], "degraded")
        self.assertEqual(
            statuses["commercial_pipeline"]["evidence"],
            ["notion:permission_required"],
        )
        self.assertEqual(statuses["publishing"]["state"], "not_connected")

    def test_unknown_domain_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Unsupported Mission Control domains"):
            self.registry.resolve({"made_up_domain": {"state": "connected", "evidence": ["x"]}})

    def test_connected_or_degraded_domain_requires_evidence(self):
        for state in ("connected", "degraded"):
            with self.subTest(state=state):
                with self.assertRaisesRegex(ValueError, "require evidence"):
                    MissionControlDomainStatus(domain="health", state=state)

    def test_invalid_state_and_evidence_shape_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "Unsupported Mission Control domain state"):
            MissionControlDomainStatus(domain="health", state="unknown")
        with self.assertRaisesRegex(ValueError, "Invalid evidence"):
            self.registry.resolve({"health": {"state": "connected", "evidence": 42}})


if __name__ == "__main__":
    unittest.main()
