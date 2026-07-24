from __future__ import annotations

import unittest

from runtime.terminology_policy import TerminologyPolicy
from runtime.tony_command_service import CommandResponse
from runtime.tony_terminology_commands import TonyTerminologyCommandService


class StubService:
    mission_control_loader = None

    def __init__(self, response: CommandResponse) -> None:
        self.response = response

    def execute(self, command, objects):
        return self.response


class TonyTerminologyCommandServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = TerminologyPolicy(
            {
                "version": "1.0.0",
                "status": "active",
                "retired_terms": [
                    {"term": "Opportunity Card", "rationale": "Retired"},
                    {"term": "Growth Sprint", "rationale": "Retired"},
                ],
            }
        )

    def test_allows_current_language(self) -> None:
        response = CommandResponse("status", "healthy", "Growth Blueprint ready.", {})
        service = TonyTerminologyCommandService(StubService(response), self.policy)
        self.assertIs(service.execute("/status", []), response)

    def test_blocks_retired_language_in_message(self) -> None:
        response = CommandResponse("status", "healthy", "Opportunity Card ready.", {})
        service = TonyTerminologyCommandService(StubService(response), self.policy)
        result = service.execute("/status", [])
        self.assertEqual(result.status, "error")
        self.assertEqual(result.data["error_code"], "terminology_violation")
        self.assertEqual(result.data["retired_terms"], ["Opportunity Card"])

    def test_blocks_retired_language_in_nested_data(self) -> None:
        response = CommandResponse(
            "status",
            "healthy",
            "Ready.",
            {"items": [{"recommended_offer": "Growth Sprint"}]},
        )
        service = TonyTerminologyCommandService(StubService(response), self.policy)
        result = service.execute("/status", [])
        self.assertEqual(result.data["retired_terms"], ["Growth Sprint"])


if __name__ == "__main__":
    unittest.main()
