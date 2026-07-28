import unittest

from runtime.terminology_policy import TerminologyPolicy
from runtime.tony_command_service import CommandResponse
from runtime.tony_terminology_commands import TonyTerminologyCommandService


class StubService:
    mission_control_loader = None

    def __init__(self, response: CommandResponse) -> None:
        self.response = response
        self.calls = 0

    def execute(self, command, objects):
        self.calls += 1
        return self.response


class TonyTerminologyCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = TerminologyPolicy({
            "version": "1.0.0",
            "version_note": "Initial canonical terminology policy.",
            "status": "active",
            "approved_terms": [
                {"term": "Growth Blueprint", "use": "Canonical strategic output"}
            ],
            "unsettled_terms": [
                {"concept": "Paid engagement", "rule": "Use descriptive language"}
            ],
            "retired_terms": [
                {"term": "Growth Sprint", "replacement": None, "rationale": "Superseded"}
            ],
        })

    def test_passes_current_language_unchanged(self) -> None:
        response = CommandResponse(command="status", status="ok", message="Growth Blueprint ready.", data={})
        service = TonyTerminologyCommandService(StubService(response), self.policy)
        self.assertIs(service.execute("/status", ()), response)

    def test_blocks_retired_language_in_nested_data(self) -> None:
        response = CommandResponse(command="status", status="ok", message="Ready.", data={"next": ["Start Growth Sprint"]})
        service = TonyTerminologyCommandService(StubService(response), self.policy)
        result = service.execute("/status", ())
        self.assertEqual(result.status, "error")
        self.assertEqual(result.data["error_code"], "terminology_violation")
        self.assertEqual(result.data["retired_terms"], ["Growth Sprint"])

    def test_vocabulary_returns_repository_policy_without_delegation(self) -> None:
        response = CommandResponse(command="status", status="ok", message="unused", data={})
        stub = StubService(response)
        service = TonyTerminologyCommandService(stub, self.policy)

        result = service.execute("/vocabulary", ())

        self.assertEqual(result.command, "vocabulary")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["policy_version"], "1.0.0")
        self.assertEqual(result.data["version_note"], "Initial canonical terminology policy.")
        self.assertIn("Version note: Initial canonical terminology policy.", result.message)
        self.assertIn("Growth Blueprint", result.message)
        self.assertIn("Paid engagement", result.message)
        self.assertIn("Growth Sprint", result.message)
        self.assertEqual(stub.calls, 0)

    def test_vocabulary_aliases_are_canonicalised(self) -> None:
        response = CommandResponse(command="status", status="ok", message="unused", data={})
        service = TonyTerminologyCommandService(StubService(response), self.policy)
        for alias in ("/terminology", "/canon"):
            self.assertEqual(service.execute(alias, ()).command, "vocabulary")


if __name__ == "__main__":
    unittest.main()
