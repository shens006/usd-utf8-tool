import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from usd_cli import main
from usd_env import runtime_report
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

ROOT = Path(__file__).parent


class CLITests(unittest.TestCase):
    def run_cli(self, *args, no_site=False):
        return subprocess.run([sys.executable] + (["-S"] if no_site else []) +
                              [str(ROOT / "usd_cli.py"), *args],
                              capture_output=True, text=True, encoding="utf-8")

    def test_version_and_help_without_sdk(self):
        version = self.run_cli("--version", no_site=True)
        self.assertEqual(version.returncode, 0)
        self.assertIn("0.2.0", version.stdout)
        help_result = self.run_cli("scan", "--help", no_site=True)
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("--json", help_result.stdout)

    def test_missing_sdk_doctor_has_install_steps(self):
        result = self.run_cli("doctor", "--json", no_site=True)
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertFalse(report["ready"])
        self.assertIn("pip", str(report["installation"]))
        self.assertIn("venv", str(report["installation"]))
        self.assertIn("https://www.python.org/downloads/", str(report["installation"]))

    def test_scan_missing_sdk_reports_install_without_traceback(self):
        result = self.run_cli("scan", str(ROOT / "examples"), no_site=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("doctor", result.stderr)
        self.assertIn("pip install", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_unsupported_python_rejected_before_import(self):
        out, err = StringIO(), StringIO()
        with patch("sys.version_info", (3, 9)), redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main(["doctor"]), 2)
        self.assertIn("3.10", err.getvalue())

    def test_doctor_sdk_matches_readiness(self):
        report = runtime_report()
        self.assertEqual(report["ready"], all(x["status"] != "error" for x in report["checks"]))

    def test_human_doctor_has_summary(self):
        result = self.run_cli("doctor", no_site=True)
        self.assertIn("环境未就绪", result.stdout)
        self.assertIn("安装步骤", result.stdout)


if __name__ == "__main__":
    unittest.main()
