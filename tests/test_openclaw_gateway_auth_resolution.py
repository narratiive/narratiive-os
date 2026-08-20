from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openclaw.tony_agent_gateway import TonyAgentGatewayConfig, openclaw_config_path, resolve_gateway_bearer


class OpenClawGatewayAuthResolutionTests(unittest.TestCase):
    def _config(self, root: str, auth: dict) -> Path:
        path = Path(root) / "openclaw.json"
        path.write_text(json.dumps({"gateway": {"auth": auth}}), encoding="utf-8")
        return path

    def test_process_token_wins_over_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(tmp, {"mode": "token", "token": "config-token"})
            credential, source = resolve_gateway_bearer(
                {"OPENCLAW_GATEWAY_TOKEN": "env-token"},
                path,
            )
        self.assertEqual(credential, "env-token")
        self.assertEqual(source, "env:OPENCLAW_GATEWAY_TOKEN")

    def test_reads_token_from_active_openclaw_config_when_runtime_env_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(tmp, {"mode": "token", "token": "configured-token"})
            credential, source = resolve_gateway_bearer({}, path)
        self.assertEqual(credential, "configured-token")
        self.assertEqual(source, "config:gateway.auth.token")

    def test_password_mode_uses_bearer_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(tmp, {"mode": "password", "password": "configured-password"})
            credential, source = resolve_gateway_bearer({}, path)
        self.assertEqual(credential, "configured-password")
        self.assertEqual(source, "config:gateway.auth.password")

    def test_env_secret_reference_is_resolved_without_printing_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(
                tmp,
                {"mode": "token", "token": {"source": "env", "provider": "default", "id": "TONY_GATEWAY_SECRET"}},
            )
            credential, source = resolve_gateway_bearer({"TONY_GATEWAY_SECRET": "secret-value"}, path)
        self.assertEqual(credential, "secret-value")
        self.assertEqual(source, "config:gateway.auth.token")
        self.assertNotIn("secret-value", source)

    def test_none_mode_requires_no_bearer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(tmp, {"mode": "none"})
            credential, source = resolve_gateway_bearer({}, path)
        self.assertEqual(credential, "")
        self.assertEqual(source, "config:none")

    def test_config_path_matches_openclaw_supported_overrides(self):
        self.assertEqual(
            openclaw_config_path({"OPENCLAW_CONFIG_PATH": "/tmp/custom.json"}),
            Path("/tmp/custom.json"),
        )
        self.assertEqual(
            openclaw_config_path({"OPENCLAW_STATE_DIR": "/tmp/state"}),
            Path("/tmp/state/openclaw.json"),
        )
        self.assertEqual(
            openclaw_config_path({"OPENCLAW_HOME": "/tmp/home"}),
            Path("/tmp/home/.openclaw/openclaw.json"),
        )

    def test_tony_runtime_uses_same_configured_credential_automatically(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(tmp, {"mode": "token", "token": "configured-token"})
            with mock.patch("openclaw.tony_agent_gateway.openclaw_config_path", return_value=path):
                config = TonyAgentGatewayConfig.from_env({})
        self.assertEqual(config.gateway_token, "configured-token")
        self.assertEqual(config.gateway_auth_source, "config:gateway.auth.token")


if __name__ == "__main__":
    unittest.main()
