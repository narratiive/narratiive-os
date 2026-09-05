from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "openclaw" / "plugins" / "narratiive-control-plane" / "bridge-auth.js"


class OpenClawBridgeAuthTests(unittest.TestCase):
    def _node(self, expression: str) -> str:
        node = shutil.which("node")
        if not node:
            self.skipTest("node is unavailable")
        script = (
            f'import {{ parseRuntimeEnvValue, resolveBridgeToken }} from {json.dumps(MODULE.resolve().as_uri())}; '
            f"console.log(JSON.stringify({expression}));"
        )
        completed = subprocess.run(
            [node, "--input-type=module", "-e", script],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_parser_reads_only_the_named_export_without_evaluating_shell(self) -> None:
        contents = "# ignored\nexport OTHER=value\nexport TONY_BRIDGE_TOKEN='safe-test-token'\n"
        value = self._node(f"parseRuntimeEnvValue({json.dumps(contents)})")
        self.assertEqual(value, "safe-test-token")

    def test_process_environment_takes_precedence_over_file_fallback(self) -> None:
        expression = (
            "resolveBridgeToken({"
            "env:{TONY_BRIDGE_TOKEN:'inherited-test-token'},"
            "readFile:()=>{throw new Error('must not read file')},"
            "homeDir:'/safe/home'"
            "})"
        )
        self.assertEqual(self._node(expression), "inherited-test-token")

    def test_canonical_runtime_file_is_used_without_executing_it(self) -> None:
        expression = (
            "resolveBridgeToken({"
            "env:{},"
            "readFile:(filename)=>filename==='/safe/home/.config/narratiive/runtime.env'"
            "?\"TONY_BRIDGE_TOKEN=canonical-test-token\\nUNRELATED=$(unsafe)\":'',"
            "homeDir:'/safe/home'"
            "})"
        )
        self.assertEqual(self._node(expression), "canonical-test-token")

    def test_missing_runtime_file_fails_closed_without_a_token(self) -> None:
        expression = "resolveBridgeToken({env:{},readFile:()=>{throw new Error('missing')},homeDir:'/safe/home'})"
        self.assertEqual(self._node(expression), "")


if __name__ == "__main__":
    unittest.main()
