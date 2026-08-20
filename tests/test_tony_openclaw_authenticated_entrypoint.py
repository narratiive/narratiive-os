from __future__ import annotations

import pathlib
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


if __name__ == "__main__":
    unittest.main()
