from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_commercial_close import TonyCommercialCloseCommandService


class FakeService:
    mission_control_loader = None
    github_configured = False

    def __init__(self, response: CommandResponse) -> None:
        self.response = response
        self.calls: list[str] = []

    def execute(self, command, objects):
        self.calls.append(command)
        return self.response


def acceptance_response() -> CommandResponse:
    return CommandResponse(
        "proposal_outcome",
        "healthy",
        "Verified acceptance intent.",
        {
            "execution_status": "proposal_outcome_verified",
            "proposal_outcome": {
                "gmail_message_id": "proposal-msg-1",
                "lead_id": "lead-1",
                "contact": "Alex Smith",
                "company": "Acme",
            },
            "gmail_reply_evidence": {
                "verified": True,
                "read_only": True,
                "message_id": "accept-msg-1",
                "thread_id": "thread-1",
                "content": "We'd like to proceed with the proposal.",
            },
            "commercial_judgement": {"disposition": "proposal_acceptance_intent", "deal_won": False},
            "external_action_taken": False,
        },
    )


def verified_notion():
    writes = []

    def notion(dispatch):
        writes.append(dispatch)
        kind = dispatch.get("payload", {}).get("kind")
        if kind == "commercial_close_state_update":
            return {"verified": True, "updated": True, "mutation_count": 1, "record_id": "notion-record-1", "status": "Won"}
        if kind == "client_onboarding_kickoff":
            return {"verified": True, "created": True, "mutation_count": 1, "record_id": "onboarding-record-1", "onboarding_status": "Started"}
        raise AssertionError(f"unexpected dispatch kind: {kind}")

    return writes, notion


class TonyCommercialCloseTests(unittest.TestCase):
    def test_acceptance_intent_requires_explicit_close_attestation(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyCommercialCloseCommandService(FakeService(acceptance_response()), dispatchers={}, store_path=Path(tmp) / "close.json")
            response = service.execute("check proposal reply", ())
        self.assertEqual(response.data["execution_status"], "commercial_close_approval_required")
        self.assertFalse(response.data["commercial_close"]["deal_won"])
        self.assertTrue(response.data["commercial_close"]["approval_required"])
        self.assertIn("confirm commercial close", response.message.casefold())
        self.assertFalse(response.data["external_action_taken"])

    def test_generic_approval_does_not_close_the_deal(self):
        with tempfile.TemporaryDirectory() as tmp:
            inner = FakeService(acceptance_response())
            service = TonyCommercialCloseCommandService(inner, dispatchers={}, store_path=Path(tmp) / "close.json")
            service.execute("check proposal reply", ())
            response = service.execute("do that", ())
        self.assertEqual(response.data["execution_status"], "commercial_close_approval_required")
        self.assertEqual(inner.calls, ["check proposal reply", "do that"])

    def test_explicit_close_approval_fails_closed_without_notion(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyCommercialCloseCommandService(FakeService(acceptance_response()), dispatchers={}, store_path=Path(tmp) / "close.json")
            service.execute("check proposal reply", ())
            response = service.execute("confirm commercial close", ())
        self.assertEqual(response.data["execution_status"], "commercial_close_notion_dispatcher_unavailable")
        self.assertFalse(response.data["commercial_close"]["deal_won"])
        self.assertFalse(response.data["external_action_taken"])

    def test_verified_notion_won_update_makes_close_authoritative_but_does_not_start_onboarding(self):
        writes, notion = verified_notion()
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyCommercialCloseCommandService(FakeService(acceptance_response()), dispatchers={"Notion": notion}, store_path=Path(tmp) / "close.json")
            service.execute("check proposal reply", ())
            response = service.execute("confirm commercial close", ())
        self.assertEqual(len(writes), 1)
        dispatch = writes[0]
        self.assertEqual(dispatch["execution_mode"], "approval_gated_write")
        self.assertTrue(dispatch["approval_granted"])
        self.assertEqual(dispatch["approval_scope"], "verified_proposal_acceptance_commercial_close")
        self.assertEqual(dispatch["payload"]["status"], "Won")
        self.assertTrue(dispatch["payload"]["close_attestation"]["commercial_terms_confirmed"])
        self.assertEqual(response.data["execution_status"], "commercial_close_verified")
        self.assertTrue(response.data["commercial_close"]["deal_won"])
        self.assertTrue(response.data["commercial_close"]["onboarding_ready"])
        self.assertFalse(response.data["commercial_close"]["onboarding_started"])
        self.assertTrue(response.data["onboarding"]["approval_required"])
        self.assertTrue(response.data["external_action_taken"])

    def test_generic_approval_after_won_does_not_start_onboarding(self):
        writes, notion = verified_notion()
        with tempfile.TemporaryDirectory() as tmp:
            inner = FakeService(acceptance_response())
            service = TonyCommercialCloseCommandService(inner, dispatchers={"Notion": notion}, store_path=Path(tmp) / "close.json")
            service.execute("check proposal reply", ())
            service.execute("confirm commercial close", ())
            response = service.execute("do that", ())
        self.assertEqual(len(writes), 1)
        self.assertEqual(response.data["execution_status"], "onboarding_approval_required")
        self.assertFalse(response.data["onboarding"]["started"])
        self.assertIn("generic approval", response.message.casefold())

    def test_start_onboarding_requires_separate_approval_and_verified_notion_evidence(self):
        writes, notion = verified_notion()
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyCommercialCloseCommandService(FakeService(acceptance_response()), dispatchers={"Notion": notion}, store_path=Path(tmp) / "close.json")
            service.execute("check proposal reply", ())
            service.execute("confirm commercial close", ())
            response = service.execute("start onboarding", ())
        self.assertEqual(len(writes), 2)
        dispatch = writes[1]
        self.assertEqual(dispatch["approval_scope"], "verified_won_client_onboarding_kickoff")
        self.assertEqual(dispatch["payload"]["source_opportunity_record_id"], "notion-record-1")
        self.assertEqual(dispatch["payload"]["commercial_status"], "Won")
        self.assertEqual(dispatch["payload"]["onboarding_status"], "Started")
        self.assertIn("do not create google drive folders", dispatch["instruction"].casefold())
        self.assertEqual(response.data["execution_status"], "onboarding_started_verified")
        self.assertTrue(response.data["onboarding"]["started"])
        self.assertEqual(response.data["onboarding"]["onboarding_record_id"], "onboarding-record-1")
        self.assertTrue(response.data["external_action_taken"])

    def test_onboarding_state_survives_restart(self):
        writes, notion = verified_notion()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "close.json"
            first = TonyCommercialCloseCommandService(FakeService(acceptance_response()), dispatchers={"Notion": notion}, store_path=path)
            first.execute("check proposal reply", ())
            first.execute("confirm commercial close", ())
            second = TonyCommercialCloseCommandService(FakeService(acceptance_response()), dispatchers={"Notion": notion}, store_path=path)
            response = second.execute("start onboarding", ())
        self.assertEqual(response.data["execution_status"], "onboarding_started_verified")
        self.assertEqual(len(writes), 2)

    def test_onboarding_write_without_verified_started_status_fails_closed(self):
        calls = []

        def notion(dispatch):
            calls.append(dispatch)
            if dispatch["payload"]["kind"] == "commercial_close_state_update":
                return {"verified": True, "updated": True, "mutation_count": 1, "record_id": "notion-record-1", "status": "Won"}
            return {"verified": True, "created": True, "mutation_count": 1, "record_id": "onboarding-record-1", "onboarding_status": "Ready"}

        with tempfile.TemporaryDirectory() as tmp:
            service = TonyCommercialCloseCommandService(FakeService(acceptance_response()), dispatchers={"Notion": notion}, store_path=Path(tmp) / "close.json")
            service.execute("check proposal reply", ())
            service.execute("confirm commercial close", ())
            response = service.execute("start onboarding", ())
        self.assertEqual(response.data["execution_status"], "onboarding_notion_write_unverified")
        self.assertFalse(response.data["onboarding"]["started"])
        self.assertFalse(response.data["external_action_taken"])

    def test_write_without_verified_won_status_does_not_close(self):
        def notion(_dispatch):
            return {"verified": True, "updated": True, "record_id": "notion-record-1", "status": "Proposal sent"}

        with tempfile.TemporaryDirectory() as tmp:
            service = TonyCommercialCloseCommandService(FakeService(acceptance_response()), dispatchers={"Notion": notion}, store_path=Path(tmp) / "close.json")
            service.execute("check proposal reply", ())
            response = service.execute("confirm commercial close", ())
        self.assertEqual(response.data["execution_status"], "commercial_close_notion_write_unverified")
        self.assertFalse(response.data["commercial_close"]["deal_won"])
        self.assertFalse(response.data["external_action_taken"])


if __name__ == "__main__":
    unittest.main()
