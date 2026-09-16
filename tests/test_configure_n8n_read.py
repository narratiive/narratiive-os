from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.configure_n8n_read import install


class ConfigureN8NReadTests(unittest.TestCase):
    def test_install_preserves_existing_values_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env_file = root / "runtime.env"
            database = root / "database.sqlite"
            env_file.write_text("KEEP_ME=safe\nTONY_DISPATCH_N8N_MODE=old\n", encoding="utf-8")
            database.touch()

            install(env_file, database)
            install(env_file, database)

            content = env_file.read_text(encoding="utf-8")
            self.assertIn("KEEP_ME=safe", content)
            self.assertEqual(content.count("TONY_DISPATCH_N8N_MODE=local_sqlite"), 1)
            self.assertEqual(content.count("TONY_N8N_DATABASE_PATH="), 1)
            self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)

    def test_install_rejects_missing_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(FileNotFoundError):
                install(root / "runtime.env", root / "missing.sqlite")


if __name__ == "__main__":
    unittest.main()
