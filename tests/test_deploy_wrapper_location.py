from __future__ import annotations

import unittest
from pathlib import Path


class TonyDeployWrapperLocationTests(unittest.TestCase):
    def test_wrapper_resolves_repository_from_its_own_location(self) -> None:
        root = Path(__file__).resolve().parents[1]
        script = (root / "scripts" / "deploy_narratiive_os.sh").read_text(encoding="utf-8")
        self.assertIn('SCRIPT_DIR="${0:A:h}"', script)
        self.assertIn('REPO="${SCRIPT_DIR:h}"', script)
        self.assertNotIn('$HOME/Documents/narratiive-os', script)
        self.assertIn('PYTHON="$REPO/.venv/bin/python"', script)
        self.assertIn('exec "$PYTHON" "$DEPLOY" --apply', script)


if __name__ == "__main__":
    unittest.main()
