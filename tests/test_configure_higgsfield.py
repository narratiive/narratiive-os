from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.configure_higgsfield import _parse, install


class ConfigureHiggsfieldTests(unittest.TestCase):
    def test_migrates_combined_key_and_enables_models_without_exposing_duplicates(self):
        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / "runtime.env"
            env_file.write_text("KEEP=safe\nHF_API_KEY_ID=old:secret\n", encoding="utf-8")

            install(env_file, "new-id:new-secret")
            parsed = _parse(env_file.read_text(encoding="utf-8"))

            self.assertEqual(parsed["KEEP"], "safe")
            self.assertEqual(parsed["HF_KEY"], "new-id:new-secret")
            self.assertNotIn("HF_API_KEY_ID", parsed)
            self.assertEqual(parsed["TONY_DISPATCH_CREATIVE_PRODUCTION_MODE"], "higgsfield_api")
            self.assertEqual(parsed["TONY_HIGGSFIELD_IMAGE_MODEL"], "marketing-studio/image")
            self.assertEqual(parsed["TONY_HIGGSFIELD_VIDEO_MODEL"], "bytedance/seedance-2.5/text-to-video")
            self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
