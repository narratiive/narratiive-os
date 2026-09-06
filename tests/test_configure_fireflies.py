from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.configure_fireflies import install, main


class ConfigureFirefliesTests(unittest.TestCase):
    def test_install_preserves_runtime_env_and_writes_protected_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config" / "runtime.env"
            path.parent.mkdir()
            path.write_text("EXISTING=safe\nTONY_FIREFLIES_API_KEY=old-value\n", encoding="utf-8")
            install(path, "new-secret-value")
            content = path.read_text(encoding="utf-8")
            self.assertIn("EXISTING=safe", content)
            self.assertIn("TONY_DISPATCH_FIREFLIES_MODE=fireflies_api", content)
            self.assertEqual(content.count("TONY_FIREFLIES_API_KEY="), 1)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_cli_uses_hidden_input_and_does_not_render_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime.env"
            output = io.StringIO()
            with mock.patch("scripts.configure_fireflies.getpass.getpass", side_effect=["hidden-value", "hidden-value"]), mock.patch("sys.argv", ["configure_fireflies.py", "--env-file", str(path)]), contextlib.redirect_stdout(output):
                result = main()
            self.assertEqual(result, 0)
            self.assertNotIn("hidden-value", output.getvalue())

    def test_invalid_or_mismatched_secret_does_not_modify_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime.env"
            with self.assertRaises(ValueError):
                install(path, "\n")
            self.assertFalse(path.exists())
            with mock.patch("scripts.configure_fireflies.getpass.getpass", side_effect=["one", "two"]), mock.patch("sys.argv", ["configure_fireflies.py", "--env-file", str(path)]):
                with self.assertRaises(SystemExit):
                    main()
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
