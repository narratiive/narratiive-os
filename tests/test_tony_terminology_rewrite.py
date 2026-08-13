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


class TonyTerminologyRewriteTests(unittest.TestCase):
    def test_rewrites_retired_terms_in_message_and_nested_data(self) -> None:
        policy = TerminologyPolicy({
            "version": "1.0.0",
            "version_note": "Test policy.",
            "status": "active",
            "approved_terms": [],
            "unsettled_terms": [
                {"concept": "Personalised prospecting asset", "rule": "Use descriptive language"},
                {"concept": "Paid commercial engagement", "rule": "Use descriptive language"},
            ],
            "retired_terms": [
                {"term": "Opportunity Card", "replacement": "personalised prospecting asset", "rationale": "Retired"},
                {"term": "Growth Sprint", "replacement": "paid commercial engagement", "rationale": "Retired"},
            ],
        })
        response = CommandResponse(
            command="leads",
            status="healthy",
            message="Prepare an Opportunity Card before the Growth Sprint.",
            data={"next": ["Build Opportunity Card", {"stage": "Growth Sprint"}]},
        )
        service = TonyTerminologyCommandService(StubService(response), policy)

        result = service.execute("What inbound leads did we get today?", ())

        self.assertEqual(result.status, "healthy")
        self.assertEqual(
            result.message,
            "Prepare an personalised prospecting asset before the paid commercial engagement.",
        )
        self.assertEqual(result.data["next"][0], "Build personalised prospecting asset")
        self.assertEqual(result.data["next"][1]["stage"], "paid commercial engagement")
        self.assertFalse(policy.scan(result.message))

    def test_unmapped_retired_term_uses_safe_descriptive_fallback(self) -> None:
        policy = TerminologyPolicy({
            "version": "1.0.0",
            "version_note": "Test policy.",
            "status": "active",
            "approved_terms": [],
            "unsettled_terms": [],
            "retired_terms": [
                {"term": "Old Offer", "replacement": None, "rationale": "Retired"},
            ],
        })
        response = CommandResponse(command="status", status="ok", message="Sell the Old Offer.", data={})
        result = TonyTerminologyCommandService(StubService(response), policy).execute("status", ())
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.message, "Sell the current Narratiive approach.")
        self.assertFalse(policy.scan(result.message))


if __name__ == "__main__":
    unittest.main()
