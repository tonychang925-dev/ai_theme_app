import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.ncf.ncf_status_gate import scan_source


ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "tools/ncf/ncf_status_gate.py"


def run_gate(root: Path, head_sha: str, base_sha: str, baseline=ROOT / "tools/ncf/ncf-baseline.json"):
    return subprocess.run(
        [
            sys.executable,
            str(GATE),
            "--root",
            str(root),
            "--baseline",
            str(baseline),
            "--repository",
            "tonychang925-dev/ai_theme_app",
            "--event-name",
            "pull_request",
            "--base-sha",
            base_sha,
            "--head-sha",
            head_sha,
            "--github-sha",
            head_sha,
        ],
        capture_output=True,
        text=True,
    )


class NCFStatusGateTests(unittest.TestCase):
    def test_exact_candidate_passes(self):
        head = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
        base = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", head + "^"], text=True
        ).strip()
        result = run_gate(ROOT, head, base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["candidate_sha"], head)
        self.assertEqual(payload["finding_count"], 0)

    def test_sha_drift_fails_closed(self):
        head = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
        result = run_gate(ROOT, "0" * 40, head)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NCF-09-fail-closed", result.stdout)

    def test_missing_baseline_fails_closed(self):
        head = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
        result = run_gate(ROOT, head, head, baseline=Path("/definitely/missing/ncf.json"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing baseline", result.stdout)

    def test_invalid_baseline_gate_crash_fails_closed(self):
        head = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
        with tempfile.NamedTemporaryFile(suffix=".json") as baseline:
            baseline.write(b"{invalid")
            baseline.flush()
            result = run_gate(ROOT, head, head, baseline=Path(baseline.name))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid baseline", result.stdout)

    def test_fallback_marker_fails(self):
        findings = scan_source("database_service/client.py", "provider fallback = True\n")
        self.assertTrue(any(item.policy == "NCF-01-critical-fallback" for item in findings))

    def test_mock_fixture_reachability_fails(self):
        findings = scan_source("runtime_service.py", "from tests.fixtures import fake_runtime\n")
        self.assertTrue(any(item.policy == "NCF-02-test-double-production-reachability" for item in findings))

    def test_legacy_authority_fails(self):
        findings = scan_source("auth/provider.py", "legacy_authority = get_legacy()\n")
        self.assertTrue(any(item.policy == "NCF-03-legacy-authority-fallback" for item in findings))

    def test_synthetic_success_fails(self):
        findings = scan_source("market_service.py", "return synthetic_success\n")
        self.assertTrue(any(item.policy == "NCF-05-synthetic-success" for item in findings))

    def test_exception_success_fails(self):
        source = "try:\n    load()\nexcept Exception:\n    return {}\n"
        findings = scan_source("identity/provider.py", source)
        self.assertTrue(any(item.policy == "NCF-06-exception-success" for item in findings))

    def test_ambient_fallback_selection_fails(self):
        source = "path = os.getenv('LEGACY_FALLBACK_HOME')\n"
        findings = scan_source("runtime/composition.py", source)
        self.assertTrue(any(item.policy == "NCF-07-ambient-authority-selection" for item in findings))

    def test_production_test_mode_fails(self):
        findings = scan_source("database_service/client.py", "test_mode = True\n")
        self.assertTrue(any(item.policy == "NCF-08-production-test-mode" for item in findings))


if __name__ == "__main__":
    unittest.main()
