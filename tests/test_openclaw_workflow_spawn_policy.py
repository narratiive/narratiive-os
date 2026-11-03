from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "openclaw" / "plugins" / "narratiive-control-plane" / "workflow-spawn-policy.js"


class OpenClawWorkflowSpawnPolicyTests(unittest.TestCase):
    def _node_json(self, expression: str) -> object:
        node = shutil.which("node")
        if not node:
            self.skipTest("node is unavailable")
        script = (
            f'import {{ blocksSpecialistSpawn, failedCommissionEvidence, hookRunKey, retainFailedCommission }} from {json.dumps(POLICY.as_uri())}; '
            f"console.log(JSON.stringify({expression}));"
        )
        completed = subprocess.run([node, "--input-type=module", "-e", script], check=True, capture_output=True, text=True)
        return json.loads(completed.stdout)

    def test_failed_commission_blocks_same_turn_specialist_bypass(self) -> None:
        result = self._node_json(
            "blocksSpecialistSpawn(failedCommissionEvidence({details:{ok:false,message:'worker unavailable'}}, 1000), 1001)"
        )
        self.assertTrue(result)

    def test_verified_commission_does_not_block_specialist_orchestration(self) -> None:
        result = self._node_json(
            "failedCommissionEvidence({details:{ok:true,data:{commissioned:true}}}, 1000)"
        )
        self.assertIsNone(result)

    def test_long_running_same_run_remains_blocked(self) -> None:
        result = self._node_json(
            "blocksSpecialistSpawn({failedAt:1000,reason:'blocked'}, 1000 + 11*60*1000)"
        )
        self.assertTrue(result)

    def test_unrelated_success_does_not_clear_prior_failure_in_same_run(self) -> None:
        result = self._node_json(
            "blocksSpecialistSpawn(retainFailedCommission("
            "failedCommissionEvidence({details:{ok:false,message:'workflow A failed'}}, 1000),"
            "{details:{ok:true,data:{commissioned:true}}}, 2000))"
        )
        self.assertTrue(result)

    def test_session_key_is_fail_closed_fallback_when_run_id_is_absent(self) -> None:
        result = self._node_json("hookRunKey({}, {sessionKey:'agent:tony:fallback'})")
        self.assertEqual(result, "agent:tony:fallback")

    def test_plugin_cleans_guard_only_when_agent_run_ends(self) -> None:
        source = (POLICY.parent / "index.js").read_text(encoding="utf-8")
        self.assertIn('api.on("agent_end"', source)
        self.assertIn("failedCommissionRuns.delete(runId)", source)
        self.assertNotIn("while (failedCommissionRuns.size", source)


if __name__ == "__main__":
    unittest.main()
