import io
import json
import unittest
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


if __name__ == "__main__":
    unittest.main()
