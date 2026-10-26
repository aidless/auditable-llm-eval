import subprocess
import sys
import unittest
from pathlib import Path


class TestDemo(unittest.TestCase):
    def test_demo_recomputes_committed_runs(self):
        root = Path(__file__).resolve().parents[1]
        proc = subprocess.run(
            [sys.executable, "demo.py"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("0.67", proc.stdout)
        self.assertIn("0.69", proc.stdout)
        self.assertIn("match=True", proc.stdout)
        self.assertIn("0 API calls", proc.stdout)
