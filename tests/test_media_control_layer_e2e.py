from __future__ import annotations

import runpy
import unittest
from pathlib import Path


class MediaControlLayerEndToEndTests(unittest.TestCase):
    def test_northstar_certification(self) -> None:
        path = Path(__file__).resolve().parent / "e2e" / "media_control_layer_test"
        namespace = runpy.run_path(str(path), run_name="media_control_layer_certification")
        rows, evidence = namespace["run_certification"]()
        self.assertTrue(rows)
        self.assertTrue(all(row["status"] == "PASS" for row in rows))
        self.assertTrue(evidence["journal"]["ok"])
        self.assertEqual(evidence["orphaned_artefacts"], [])
        self.assertEqual(evidence["state_inconsistencies"], [])
        self.assertFalse(evidence["production_records_modified"])


if __name__ == "__main__":
    unittest.main()
