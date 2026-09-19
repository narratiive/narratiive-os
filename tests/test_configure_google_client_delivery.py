from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.configure_google_client_delivery import install


class ConfigureGoogleClientDeliveryTests(unittest.TestCase):
    def test_install_preserves_existing_values_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / "runtime.env"
            env_file.write_text(
                "KEEP=safe\nTONY_DISPATCH_CLIENT_DELIVERY_MODE=old\n",
                encoding="utf-8",
            )

            install(env_file)
            install(env_file)

            content = env_file.read_text(encoding="utf-8")
            self.assertIn("KEEP=safe", content)
            self.assertEqual(
                content.count("TONY_DISPATCH_CLIENT_DELIVERY_MODE=google_drive_gmail"),
                1,
            )
            self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
