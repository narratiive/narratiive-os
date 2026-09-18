from __future__ import annotations

import stat
import tempfile
import unittest
from pathlib import Path

from scripts.configure_document_worker import install


class ConfigureDocumentWorkerTests(unittest.TestCase):
    def test_install_is_atomic_private_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            node = root / "node"
            python = root / "python"
            modules = root / "node_modules"
            skill = root / "skill"
            node.write_text("node", encoding="utf-8")
            python.write_text("python", encoding="utf-8")
            modules.mkdir()
            skill.mkdir()
            env = root / "config" / "runtime.env"

            for _ in range(2):
                install(env, node=node, node_modules=modules, skill_dir=skill, python=python)

            contents = env.read_text(encoding="utf-8")
            self.assertEqual(contents.count("NARRATIIVE_DOCUMENT_WORKER_MODE="), 1)
            self.assertIn("NARRATIIVE_DOCUMENT_WORKER_MODE=local_artifact_tool", contents)
            self.assertEqual(stat.S_IMODE(env.stat().st_mode), 0o600)

    def test_install_rejects_missing_runtime_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "existing file"):
                install(
                    root / "runtime.env",
                    node=root / "missing-node",
                    node_modules=root,
                    skill_dir=root,
                    python=root / "missing-python",
                )


if __name__ == "__main__":
    unittest.main()
