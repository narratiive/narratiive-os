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


class TonyTerminologyCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = TerminologyPolicy({
            "version": "1.0.0",
            "status": "active",
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


if __name__ == "__main__":
    unittest.main()
