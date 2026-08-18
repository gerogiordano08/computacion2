from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


class SmokeTests(unittest.TestCase):
    def test_headless_smoke_opt_in(self) -> None:
        if os.environ.get("TP1_RUN_SMOKE") != "1":
            self.skipTest("Set TP1_RUN_SMOKE=1 to run the multiprocess smoke test.")
        repo_root = Path(__file__).resolve().parents[1]
        command = [sys.executable, "src/main.py", "--no-ui", "--duration", "2"]
        completed = subprocess.run(command, cwd=repo_root, capture_output=True, text=True, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
