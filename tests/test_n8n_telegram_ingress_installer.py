from __future__ import annotations

import importlib.util
import json
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


installer = load_module(
    "install_n8n_telegram_ingress",
    ROOT / "scripts" / "install_n8n_telegram_ingress.py",
)


class N8nTelegramIngressInstallerTests(unittest.TestCase):
    def _fixture(self, root: Path, *, telegram_enabled: bool = False):
        repo = root / "repo"
        (repo / "scripts").mkdir(parents=True)
        (repo / "scripts" / "run_with_env.py").write_text("", encoding="utf-8")
        env_file = root / "runtime.env"
        env_file.write_text("TONY_BRIDGE_TOKEN=test-only\n", encoding="utf-8")
        env_file.chmod(0o600)
        binaries = []
        for name in ("python", "node", "n8n", "ngrok"):
            path = root / name
            path.write_text("", encoding="utf-8")
            path.chmod(0o700)
            binaries.append(path)
        config = root / "openclaw.json"
        config.write_text(
            json.dumps({"channels": {"telegram": {"enabled": telegram_enabled}}}),
            encoding="utf-8",
        )
        return repo, env_file, (*binaries, config)

    def test_specs_pin_https_webhook_env_and_tunnel_hostname(self):
        specs = installer.build_specs(
            Path("/repo"),
            Path("/python"),
            Path("/env"),
            Path("/node"),
            Path("/n8n"),
            Path("/ngrok"),
            "https://tony.example.test/",
        )
        self.assertEqual(
            [item.label for item in specs],
            [installer.TUNNEL_LABEL, installer.N8N_LABEL],
        )
        self.assertIn("--url=tony.example.test", specs[0].arguments)
        self.assertIn("WEBHOOK_URL=https://tony.example.test/", specs[1].arguments)
        self.assertIn("N8N_BLOCK_ENV_ACCESS_IN_NODE=false", specs[1].arguments)
        self.assertIn(f"PATH=/:{installer.SYSTEM_PATH}", specs[1].arguments)
        self.assertEqual(specs[1].arguments[-3:], ("/node", "/n8n", "start"))

    def test_rejects_non_https_or_non_base_urls(self):
        for value in ("http://localhost:5678", "https://example.test/path", "https://example.test/?token=x"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                installer.validate_webhook_url(value)

    def test_install_writes_secret_free_plists_and_retires_legacy_poller(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, env_file, (python, node, n8n, ngrok, config) = self._fixture(root)
            home = root / "home"
            agents = home / "Library" / "LaunchAgents"
            agents.mkdir(parents=True)
            legacy = agents / f"{installer.LEGACY_POLL_LABEL}.plist"
            legacy.write_text("legacy", encoding="utf-8")
            result = installer.install(
                repo_root=repo, python_path=python, env_file=env_file, node_path=node, n8n_path=n8n,
                ngrok_path=ngrok, webhook_url="https://tony.example.test", home=home,
                activate=False, openclaw_config=config,
            )
            self.assertTrue(result["legacy_poller_removed"])
            self.assertFalse(legacy.exists())
            self.assertEqual(len(result["agents"]), 2)
            launcher = home / "Library" / "Application Support" / "Narratiive" / "run_with_env.py"
            self.assertTrue(launcher.is_file())
            for name in (installer.N8N_LABEL, installer.TUNNEL_LABEL):
                payload = plistlib.loads((agents / f"{name}.plist").read_bytes())
                rendered = json.dumps(payload)
                self.assertNotIn("test-only", rendered)
                self.assertNotIn("EnvironmentVariables", payload)
                self.assertTrue(payload["KeepAlive"])
            n8n_payload = plistlib.loads((agents / f"{installer.N8N_LABEL}.plist").read_bytes())
            self.assertIn(str(launcher), n8n_payload["ProgramArguments"])
            self.assertEqual(n8n_payload["WorkingDirectory"], str(home))

    def test_install_refuses_competing_native_openclaw_telegram(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, env_file, (python, node, n8n, ngrok, config) = self._fixture(root, telegram_enabled=True)
            with self.assertRaisesRegex(RuntimeError, "OpenClaw native Telegram is enabled"):
                installer.install(
                    repo_root=repo, python_path=python, env_file=env_file, node_path=node, n8n_path=n8n,
                    ngrok_path=ngrok, webhook_url="https://tony.example.test", home=root / "home",
                    activate=False, openclaw_config=config,
                )

    def test_install_rejects_missing_bridge_token_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, env_file, (python, node, n8n, ngrok, config) = self._fixture(root)
            env_file.write_text("OTHER=value\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "TONY_BRIDGE_TOKEN"):
                installer.install(
                    repo_root=repo, python_path=python, env_file=env_file, node_path=node, n8n_path=n8n,
                    ngrok_path=ngrok, webhook_url="https://tony.example.test", home=root / "home",
                    activate=False, openclaw_config=config,
                )


if __name__ == "__main__":
    unittest.main()
