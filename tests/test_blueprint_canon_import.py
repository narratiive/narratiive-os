from __future__ import annotations

import unittest

from scripts.import_blueprint_canon import normalize_export_bytes


class BlueprintCanonImportTests(unittest.TestCase):
    def test_normalize_export_bytes_removes_bom_and_crlf_and_ensures_final_newline(self) -> None:
        raw = "\ufeffLine 1\r\nLine 2\rLine 3".encode("utf-8")

        normalized = normalize_export_bytes(raw)

        self.assertEqual(normalized, "Line 1\nLine 2\nLine 3\n")


if __name__ == "__main__":
    unittest.main()
