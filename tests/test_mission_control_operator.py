from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from openclaw.mission_control_web import MissionControlWebApplication
from runtime.inbound_leads import InboundLead
from runtime.mission_control_operator import OperatorMissionControlProjector
from runtime.models import ArtifactRef, StageRecord, StageStatus, WorkflowState, WorkflowStatus


class MissionControlOperatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.projector = OperatorMissionControlProjector(workflow_root=self.root, workflow_workspace_id="narratiive")

    def tearDown(self):
        self.tmp.cleanup()

    def _state(self, *, client="catkin", workflow="strategy_thesis_to_growth_blueprint", status=WorkflowStatus.ACTIVE, blocked=None, approval="not_required", synthetic=False):
        scope = hashlib.sha256(f"narratiive:{client}".encode("utf-8")).hexdigest()[:24]
        artifact_dir = self.root / scope / "artifacts"
        event_dir = self.root / scope / "events"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        event_dir.mkdir(parents=True, exist_ok=True)
        artifact = artifact_dir / "artifact-v1.json"
        artifact.write_text('{"safe":true}', encoding="utf-8")
        stage = StageRecord(
            "prepare_growth_blueprint", "claude-anthropic", status=StageStatus.BLOCKED if blocked else StageStatus.RUNNING,
            started_at="2026-10-04T10:00:00+00:00", revision_count=1,
            capability="strategic_reasoning",
            output_artifacts=[ArtifactRef("artifact-v1", "workflow_step_output", str(artifact), "abc", {"parent_artifact_ids": ["parent-v0"]})],
            attempts=[{"status": "returned", "revision": 0, "quality_passed": False, "candidate_artifact": {"artifact_id": "artifact-failed", "artifact_type": "worker_attempt_output", "location": str(artifact), "checksum": "bad", "metadata": {}}}],
            quality_result={"passed": True, "failed_checks": []}, blocker=blocked,
        )
        state = WorkflowState(
            workflow, f"run-{client}", [stage], status=status, current_stage_id=stage.stage_id,
            workspace_id="narratiive", client_id=client, entity_id=client, blocker=blocked,
            approval_status=approval, proposed_next_action="Review Growth Blueprint v2.",
            input_payload={"company": "CatKin" if client == "catkin" else "Synthetic Tester", "synthetic": synthetic},
            created_at="2026-10-04T09:00:00+00:00", updated_at="2026-10-04T11:00:00+00:00",
        )
        (event_dir / f"{state.run_id}.jsonl").write_text(json.dumps({"event_id":"evt-1","run_id":state.run_id,"event_type":"stage.quality_recorded","payload":{"passed":False},"occurred_at":"2026-10-04T10:30:00+00:00","workspace_id":"narratiive"})+"\n", encoding="utf-8")
        return state

    def test_projects_live_truth_quality_revisions_and_human_gate(self):
        state = self._state(status=WorkflowStatus.AWAITING_APPROVAL, approval="pending")
        result = self.projector.project(states=[state], leads=[], system_snapshot={"status":"healthy","connections":[]}, generated_at="2026-10-04T12:00:00Z")
        self.assertEqual(result["summary"], {"active_opportunities":1,"waiting_for_matt":1,"blocked":0,"running_autonomously":0,"synthetic_hidden":0})
        item = result["opportunities"][0]
        self.assertEqual(item["lifecycle_stage"], "delivery")
        self.assertTrue(item["requires_matt"])
        self.assertEqual(item["next_action"], "Review Growth Blueprint v2.")
        self.assertEqual(item["artefacts"][-1]["version"], 2)
        self.assertEqual(item["artefacts"][-1]["quality_status"], "passed")
        self.assertTrue(any(not row["passed"] for row in item["quality_history"]))
        self.assertEqual(item["activity"][0]["label"], "Quality review failed")
        self.assertNotIn("approval_token", json.dumps(result))

    def test_synthetic_is_labelled_and_excluded_from_executive_counts(self):
        live = self._state()
        test = self._state(client="fixture", synthetic=True)
        lead = InboundLead("fixture", "Tester", company="Synthetic Tester", disposition="test")
        result = self.projector.project(states=[live, test], leads=[lead], generated_at="2026-10-04T12:00:00Z")
        self.assertEqual(result["summary"]["active_opportunities"], 1)
        self.assertEqual(result["summary"]["synthetic_hidden"], 1)
        self.assertEqual([item["id"] for item in result["opportunities"]], ["catkin"])

    def test_archived_suppressed_and_completed_leads_do_not_enter_projection(self):
        states = [
            self._state(client="archived"),
            self._state(client="suppressed"),
            self._state(client="completed"),
            self._state(client="live"),
        ]
        leads = [
            InboundLead("archived", "Archived", disposition="archived"),
            InboundLead("suppressed", "Suppressed", disposition="suppressed"),
            InboundLead("completed", "Completed", status="Completed"),
            InboundLead("live", "Live"),
        ]

        result = self.projector.project(states=states, leads=leads, generated_at="2026-10-04T12:00:00Z")

        self.assertEqual([item["id"] for item in result["opportunities"]], ["live"])
        self.assertEqual(result["summary"]["active_opportunities"], 1)
        self.assertEqual(result["summary"]["synthetic_hidden"], 3)
        self.assertTrue(all(item["company"] == "Live" for item in result["activity"]))

    def test_artifact_route_rejects_unprojected_foreign_scope(self):
        state = self._state()
        foreign = self.root / "foreign" / "artifacts" / "artifact-foreign.json"
        foreign.parent.mkdir(parents=True)
        foreign.write_text('{"foreign":true}', encoding="utf-8")
        app = MissionControlWebApplication(
            lambda: self.projector.project(states=[state], leads=[]),
            workflow_root=self.root,
        )
        status = {}

        body = app.handle(
            {"REQUEST_METHOD":"GET","PATH_INFO":"/mission-control/artifact","QUERY_STRING":"artifact_id=artifact-foreign","REMOTE_ADDR":"127.0.0.1"},
            lambda value, headers: status.update(value=value, headers=headers),
        )

        self.assertTrue(status["value"].startswith("404"))
        self.assertEqual(b"".join(body), b"Artefact unavailable")

    def test_artifact_route_rejects_projected_reference_to_sibling_client_scope(self):
        state = self._state()
        foreign_scope = hashlib.sha256(b"narratiive:foreign-client").hexdigest()[:24]
        foreign = self.root / foreign_scope / "artifacts" / "artifact-foreign.json"
        foreign.parent.mkdir(parents=True)
        foreign.write_text('{"foreign":true}', encoding="utf-8")
        state.stage(state.current_stage_id).output_artifacts = [
            ArtifactRef("artifact-foreign", "workflow_step_output", str(foreign), "foreign", {})
        ]
        app = MissionControlWebApplication(
            lambda: self.projector.project(states=[state], leads=[]),
            workflow_root=self.root,
        )
        status = {}

        snapshot = self.projector.project(states=[state], leads=[])
        body = app.handle(
            {"REQUEST_METHOD":"GET","PATH_INFO":"/mission-control/artifact","QUERY_STRING":"artifact_id=artifact-foreign","REMOTE_ADDR":"127.0.0.1"},
            lambda value, headers: status.update(value=value, headers=headers),
        )

        projected = next(
            item
            for item in snapshot["opportunities"][0]["artefacts"]
            if item["artifact_id"] == "artifact-foreign"
        )
        self.assertIsNone(projected["open_url"])
        self.assertTrue(status["value"].startswith("404"))
        self.assertEqual(b"".join(body), b"Artefact unavailable")

    def test_artifact_route_serves_only_projected_artifact(self):
        state = self._state()
        app = MissionControlWebApplication(
            lambda: self.projector.project(states=[state], leads=[]),
            workflow_root=self.root,
        )
        status = {}

        body = app.handle(
            {"REQUEST_METHOD":"GET","PATH_INFO":"/mission-control/artifact","QUERY_STRING":"artifact_id=artifact-v1","REMOTE_ADDR":"127.0.0.1"},
            lambda value, headers: status.update(value=value, headers=headers),
        )

        self.assertTrue(status["value"].startswith("200"))
        self.assertEqual(json.loads(b"".join(body)), {"safe": True})

    def test_connection_projection_uses_only_canonical_states(self):
        result = self.projector.project(
            states=[self._state()],
            leads=[],
            system_snapshot={
                "connections": [
                    {"name": "Google Ads", "state": "healthy_live", "evidence": "verified"},
                    {"name": "Runtime", "state": "connected"},
                ]
            },
        )

        self.assertEqual(
            [item["state"] for item in result["system"]["connections"]],
            ["unknown", "connected"],
        )

    def test_blocker_and_operational_substate_are_visible(self):
        state = self._state(status=WorkflowStatus.BLOCKED, blocked="quality_failed:evidence_specificity")
        item = self.projector.project(states=[state], leads=[])["opportunities"][0]
        self.assertEqual(item["attention_state"], "blocked")
        self.assertEqual(item["operational_substate"], "blocked")
        self.assertIn("evidence_specificity", item["blocker"])

    def test_web_is_loopback_read_only_and_viewing_does_not_mutate_state(self):
        state = self._state()
        watched = next(self.root.glob("*/artifacts/*.json"))
        before = hashlib.sha256(watched.read_bytes()).hexdigest(), watched.stat().st_mtime_ns
        app = MissionControlWebApplication(lambda: self.projector.project(states=[state], leads=[]), workflow_root=self.root)
        status = {}
        body = app.handle({"REQUEST_METHOD":"GET","PATH_INFO":"/mission-control/api","REMOTE_ADDR":"127.0.0.1"}, lambda value, headers: status.update(value=value, headers=headers))
        self.assertTrue(status["value"].startswith("200"))
        self.assertTrue(json.loads(b"".join(body))["capabilities"]["read_only"])
        after = hashlib.sha256(watched.read_bytes()).hexdigest(), watched.stat().st_mtime_ns
        self.assertEqual(before, after)
        body = app.handle({"REQUEST_METHOD":"POST","PATH_INFO":"/mission-control/api","REMOTE_ADDR":"127.0.0.1","wsgi.input":io.BytesIO()}, lambda value, headers: status.update(value=value, headers=headers))
        self.assertTrue(status["value"].startswith("405"))
        self.assertEqual(b"".join(body), b"Read-only interface")
        app.handle({"REQUEST_METHOD":"GET","PATH_INFO":"/mission-control","REMOTE_ADDR":"10.0.0.2"}, lambda value, headers: status.update(value=value, headers=headers))
        self.assertTrue(status["value"].startswith("403"))

    def test_restart_reprojection_preserves_displayed_truth(self):
        state = self._state()
        first = self.projector.project(states=[state], leads=[], generated_at="2026-10-04T12:00:00Z")
        restarted = OperatorMissionControlProjector(workflow_root=self.root, workflow_workspace_id="narratiive")
        second = restarted.project(states=[state], leads=[], generated_at="2026-10-04T12:00:00Z")
        self.assertEqual(first, second)

    def test_overdue_running_stage_is_labelled_stalled_from_runtime_timeout_evidence(self):
        state = self._state()
        projector = OperatorMissionControlProjector(
            workflow_root=self.root,
            workflow_workspace_id="narratiive",
            worker_timeout_seconds={"strategic_reasoning": 180},
        )
        item = projector.project(
            states=[state],
            leads=[],
            generated_at="2026-10-04T12:00:00Z",
        )["opportunities"][0]
        self.assertEqual(item["attention_state"], "stalled")
        self.assertEqual(item["operational_substate"], "stalled")
        self.assertEqual(item["current_activity"], "Growth Blueprint stalled")
        self.assertFalse(item["blocked"])

    def test_recovered_stage_is_retrying_not_running(self):
        state = self._state()
        stage = state.stage(state.current_stage_id)
        stage.status = StageStatus.READY
        stage.retry_count = 1
        item = self.projector.project(states=[state], leads=[])["opportunities"][0]
        self.assertEqual(item["attention_state"], "retrying")
        self.assertEqual(item["operational_substate"], "retrying")
        self.assertIn("governed retry ready", item["current_activity"])


if __name__ == "__main__":
    unittest.main()
