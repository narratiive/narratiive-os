from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest


class TonyAuthenticatedEntrypointTests(unittest.TestCase):
    def test_entrypoint_uses_shared_gateway_auth_resolver_without_printing_secret(self):
        path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "check_tony_openclaw_live_authenticated.py"
        source = path.read_text(encoding="utf-8")
        self.assertIn("resolve_gateway_bearer", source)
        self.assertIn('report["gateway_auth_present"]', source)
        self.assertIn('report["gateway_auth_source"]', source)
        self.assertNotIn('report["gateway_token"]', source)
        self.assertNotIn('report["gateway_password"]', source)

    def test_entrypoint_can_be_invoked_directly_from_outside_repo(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        script = root / "scripts" / "check_tony_openclaw_live_authenticated.py"
        with tempfile.TemporaryDirectory() as cwd:
            completed = subprocess.run(
                [sys.executable, str(script), "--help"],
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Run Tony's live OpenClaw acceptance probe", completed.stdout)
        self.assertNotIn("ModuleNotFoundError", completed.stderr)


if __name__ == "__main__":
    unittest.main()
