import tempfile
import unittest
from pathlib import Path

from runtime.executive_memory import ExecutiveMemoryStore, MemoryKind, MemoryScope
from runtime.tony_command_service import CommandResponse
from runtime.tony_memory_commands import TonyMemoryCommandService


class StubCommandService:
    mission_control_loader = object()
    github_configured = True

    def execute(self, command, objects):
        name = command.strip().split(" ", 1)[0].lstrip("/")
        return CommandResponse(name, "ok", "Base response.", {"objects": list(objects)})


class TonyMemoryCommandServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "memory.jsonl"
        self.store = ExecutiveMemoryStore(self.path)
        self.service = TonyMemoryCommandService(StubCommandService(), self.store)

    def tearDown(self):
        self.temp.cleanup()

    def test_remember_persists_decision_across_service_restart(self):
        response = self.service.execute("/remember decision Prioritise client delivery", [])
        self.assertEqual(response.status, "ok")

        restarted = TonyMemoryCommandService(
            StubCommandService(), ExecutiveMemoryStore(self.path)
        )
        recalled = restarted.execute("/memory", [])
        self.assertIn("Prioritise client delivery", recalled.message)

    def test_operational_response_includes_relevant_continuity(self):
        self.store.append(
            kind=MemoryKind.COMMITMENT,
            summary="Send the approved proposal",
            importance=4,
        )
        response = self.service.execute("/next", [])
        self.assertIn("Continuity:", response.message)
        self.assertIn("Send the approved proposal", response.message)
        self.assertEqual(
            response.data["executive_memory"],
            ["commitment: Send the approved proposal"],
        )

    def test_client_scope_does_not_leak(self):
        self.store.append(
            kind=MemoryKind.CONTEXT,
            summary="Rave requires final creative",
            scope=MemoryScope(client_id="rave"),
            importance=4,
        )
        rave = self.service.execute("/client Rave", [])
        other = self.service.execute("/client Other", [])
        self.assertIn("Rave requires final creative", rave.message)
        self.assertNotIn("Rave requires final creative", other.message)

    def test_approval_is_marked_as_requiring_matt(self):
        self.service.execute("/remember approval Merge release candidate", [])
        records = self.store.select(
            scope=MemoryScope(),
            kinds=(MemoryKind.APPROVAL,),
            requires_matt=True,
        )
        self.assertEqual(len(records), 1)

    def test_invalid_remember_command_fails_closed(self):
        response = self.service.execute("/remember maybe something", [])
        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "invalid_memory_command")


if __name__ == "__main__":
    unittest.main()
