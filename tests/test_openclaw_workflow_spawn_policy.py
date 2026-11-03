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
            f'import {{ blocksSpecialistSpawn, failedCommissionEvidence }} from {json.dumps(POLICY.as_uri())}; '
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

    def test_stale_failure_does_not_block_future_turn(self) -> None:
        result = self._node_json(
            "blocksSpecialistSpawn({failedAt:1000,reason:'blocked'}, 1000 + 11*60*1000)"
        )
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()

