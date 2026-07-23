import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError

from scripts.service_doctor import ServiceDoctor


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status = status
        self.payload = payload if payload is not None else {"ok": True}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def getcode(self):
        return self.status

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class ServiceDoctorTests(unittest.TestCase):
    def test_all_services_healthy(self):
        doctor = ServiceDoctor(opener=lambda endpoint, timeout: FakeResponse())
        exit_code, report = doctor.run("http://gateway/health", "http://bridge/health")
        self.assertEqual(exit_code, 0)
        self.assertTrue(report["ok"])
        self.assertEqual([item["healthy"] for item in report["services"]], [True, True])

    def test_gateway_failure_has_stable_exit_code(self):
        def opener(endpoint, timeout):
            if "gateway" in endpoint:
                raise URLError("refused")
            return FakeResponse()

        exit_code, report = ServiceDoctor(opener=opener).run(
            "http://gateway/health", "http://bridge/health"
        )
        self.assertEqual(exit_code, 10)
        self.assertFalse(report["services"][0]["healthy"])
        self.assertTrue(report["services"][1]["healthy"])

    def test_bridge_failure_has_stable_exit_code(self):
        def opener(endpoint, timeout):
            if "bridge" in endpoint:
                raise TimeoutError("timed out")
            return FakeResponse()

        exit_code, report = ServiceDoctor(opener=opener).run(
            "http://gateway/health", "http://bridge/health"
        )
        self.assertEqual(exit_code, 20)
        self.assertTrue(report["services"][0]["healthy"])
        self.assertFalse(report["services"][1]["healthy"])

    def test_both_failures_have_combined_exit_code(self):
        def opener(endpoint, timeout):
            raise URLError("refused")

        exit_code, report = ServiceDoctor(opener=opener).run(
            "http://gateway/health", "http://bridge/health"
        )
        self.assertEqual(exit_code, 30)
        self.assertFalse(report["ok"])

    def test_non_ok_payload_is_unhealthy(self):
        doctor = ServiceDoctor(opener=lambda endpoint, timeout: FakeResponse(payload={"ok": False}))
        exit_code, report = doctor.run("http://gateway/health", "http://bridge/health")
        self.assertEqual(exit_code, 30)
        self.assertEqual(report["services"][0]["error"], "unhealthy response")

    def test_matching_deployment_receipt_is_healthy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "runtime-state" / "deployment.json"
            state.parent.mkdir()
            state.write_text(json.dumps({
                "status": "healthy",
                "deployed_revision": "abc123",
                "deployed_at": "2026-07-23T12:00:00Z",
            }), encoding="utf-8")
            doctor = ServiceDoctor(
                opener=lambda endpoint, timeout: FakeResponse(),
                revision_reader=lambda repository: "abc123",
            )
            exit_code, report = doctor.run(
                "http://gateway/health",
                "http://bridge/health",
                repository_root=root,
            )
            self.assertEqual(exit_code, 0)
            self.assertTrue(report["deployment"]["healthy"])
            self.assertEqual(report["deployment"]["current_revision"], "abc123")

    def test_stale_deployment_receipt_has_distinct_exit_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "runtime-state" / "deployment.json"
            state.parent.mkdir()
            state.write_text(json.dumps({
                "status": "healthy",
                "deployed_revision": "old123",
                "deployed_at": "2026-07-23T12:00:00Z",
            }), encoding="utf-8")
            doctor = ServiceDoctor(
                opener=lambda endpoint, timeout: FakeResponse(),
                revision_reader=lambda repository: "new456",
            )
            exit_code, report = doctor.run(
                "http://gateway/health",
                "http://bridge/health",
                repository_root=root,
            )
            self.assertEqual(exit_code, 40)
            self.assertFalse(report["ok"])
            self.assertIn("live deployment is stale", report["deployment"]["error"])

    def test_missing_receipt_combines_with_service_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def opener(endpoint, timeout):
                if "gateway" in endpoint:
                    raise URLError("refused")
                return FakeResponse()

            doctor = ServiceDoctor(opener=opener, revision_reader=lambda repository: "abc123")
            exit_code, report = doctor.run(
                "http://gateway/health",
                "http://bridge/health",
                repository_root=root,
            )
            self.assertEqual(exit_code, 50)
            self.assertFalse(report["deployment"]["healthy"])
            self.assertIn("receipt missing", report["deployment"]["error"])

    def test_incomplete_receipt_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "runtime-state" / "deployment.json"
            state.parent.mkdir()
            state.write_text(json.dumps({"status": "healthy"}), encoding="utf-8")
            doctor = ServiceDoctor(
                opener=lambda endpoint, timeout: FakeResponse(),
                revision_reader=lambda repository: "abc123",
            )
            exit_code, report = doctor.run(
                "http://gateway/health",
                "http://bridge/health",
                repository_root=root,
            )
            self.assertEqual(exit_code, 40)
            self.assertIn("incomplete", report["deployment"]["error"])


if __name__ == "__main__":
    unittest.main()
