from __future__ import annotations

import importlib.util
import os
import plistlib
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


installer = load_module("install_launch_agents", ROOT / "scripts" / "install_launch_agents.py")
launcher = load_module("run_with_env", ROOT / "scripts" / "run_with_env.py")


class LaunchdInstallerTests(unittest.TestCase):
    def test_specs_include_runtime_bridge_and_supervisor(self) -> None:
        specs = installer.build_specs(Path("/repo"), Path("/python"), Path("/env"))
        self.assertEqual(
            [spec.label for spec in specs],
            [
                "com.narratiive.runtime",
                "com.narratiive.tony-http-bridge",
                "com.narratiive.service-supervisor",
            ],
        )
        self.assertTrue(specs[0].keep_alive)
        self.assertTrue(specs[1].keep_alive)
        self.assertTrue(specs[1].arguments[-1].endswith("openclaw/tony_live_bridge.py"))
        self.assertFalse(specs[2].keep_alive)
        self.assertEqual(specs[2].start_interval, 60)

    def test_plist_contains_no_secret_values(self) -> None:
        spec = installer.build_specs(Path("/repo"), Path("/python"), Path("/secure/runtime.env"))[0]
        rendered = installer.render_plist(spec, Path("/repo"), Path("/logs"))
        payload = plistlib.loads(rendered)
        self.assertEqual(payload["Label"], "com.narratiive.runtime")
        self.assertNotIn("EnvironmentVariables", payload)
        self.assertIn("/secure/runtime.env", payload["ProgramArguments"])

    def test_install_writes_three_valid_plists_without_activation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "runtime").mkdir(parents=True)
            (repo / "openclaw").mkdir(parents=True)
            (repo / "scripts").mkdir(parents=True)
            for path in (
                repo / "runtime" / "server.py",
                repo / "openclaw" / "tony_live_bridge.py",
                repo / "scripts" / "service_supervisor.py",
                repo / "scripts" / "run_with_env.py",
            ):
                path.write_text("", encoding="utf-8")
            python_path = root / "python3"
            python_path.write_text("", encoding="utf-8")
            env_file = root / "runtime.env"
            env_file.write_text("NARRATIIVE_API_KEY=test\n", encoding="utf-8")
            env_file.chmod(0o600)
            home = root / "home"
            written = installer.install(repo, python_path, env_file, home, activate=False)
            self.assertEqual(len(written), 3)
            for path in written:
                self.assertTrue(path.exists())
                plistlib.loads(path.read_bytes())

    def test_install_rejects_insecure_environment_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "runtime").mkdir(parents=True)
            (repo / "openclaw").mkdir(parents=True)
            (repo / "runtime" / "server.py").write_text("", encoding="utf-8")
            (repo / "openclaw" / "tony_live_bridge.py").write_text("", encoding="utf-8")
            python_path = root / "python3"
            python_path.write_text("", encoding="utf-8")
            env_file = root / "runtime.env"
            env_file.write_text("SECRET=value\n", encoding="utf-8")
            env_file.chmod(0o644)
            with self.assertRaises(PermissionError):
                installer.install(repo, python_path, env_file, root / "home", activate=False)

    def test_env_loader_parses_values_and_comments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.env"
            path.write_text("# comment\nA=one\nB=two=three\n", encoding="utf-8")
            path.chmod(0o600)
            self.assertEqual(launcher.load_env_file(path), {"A": "one", "B": "two=three"})

    def test_env_loader_rejects_insecure_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.env"
            path.write_text("A=one\n", encoding="utf-8")
            path.chmod(0o644)
            with self.assertRaises(PermissionError):
                launcher.load_env_file(path)

    def test_uninstall_removes_known_agents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            agents = home / "Library" / "LaunchAgents"
            agents.mkdir(parents=True)
            for label in (
                "com.narratiive.runtime",
                "com.narratiive.tony-http-bridge",
                "com.narratiive.service-supervisor",
            ):
                (agents / f"{label}.plist").write_text("test", encoding="utf-8")
            removed = installer.uninstall(home, deactivate=False)
            self.assertEqual(len(removed), 3)
            self.assertFalse(any(path.exists() for path in removed))


if __name__ == "__main__":
    unittest.main()
