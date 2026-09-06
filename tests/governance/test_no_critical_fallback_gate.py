import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCANNER = ROOT / "tools" / "no_critical_fallback_gate.py"
AUTHORIZATION = "EXPLICIT_TONY_GO_NCF_A5_LOCAL_CODEX_CI_GITHUB_ENFORCEMENT"
RULE_CASES = {
    "NCF-01": "from tests.mock_provider import provider\n",
    "NCF-02": "try:\n    from canonical import Provider\nexcept ImportError:\n    provider = FakeProvider()\n",
    "NCF-03": "import os\nDB = os.getenv('DB_TYPE', 'memory')\n",
    "NCF-04": "def provider_result():\n    try:\n        return call()\n    except Exception:\n        return True\n",
    "NCF-05": "persona_fallback = build_persona()\n",
    "NCF-06": "provider = fallback_provider\n",
    "NCF-07": "def get_provider():\n    if provider is None:\n        provider = Provider()\n    return provider\n",
    "NCF-08": "storage = legacy_storage\n",
    "NCF-09": "legacy_from_execution = result\n",
    "NCF-10": "if asset_missing: return None\n",
    "NCF-11": "provenance = 'unknown'\n",
    "NCF-12": "result = 'outer success with inner unavailable'\n",
    "NCF-13": "TEST_MODE = True\n",
    "NCF-14": "def render(provider_error, stream):\n    return assistant_text_after_provider_failure(provider_error, stream)\n",
    "NCF-15": "import sys\nsys.path.insert(0, '/tmp/test')\n",
    "NCF-16": "if conversation_missing: use_legacy_history()\n",
}


class NoCriticalFallbackSabotageTests(unittest.TestCase):
    TEST_CLASS = "BOUNDARY_CONTRACT"
    MOCK_USED = "NO"
    FIXTURE_USED = "NO"
    REAL_PROVIDER_USED = "NO"
    REAL_DATABASE_USED = "NO"
    REAL_NETWORK_USED = "NO"
    CANONICAL_PATH_USED = "NO"

    def run_scanner(self, source: str, relative_path: str = "julia_core/provider.py"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            production = root / relative_path
            production.parent.mkdir(parents=True)
            production.write_text(source, encoding="utf-8")
            baseline = root / "ncf-baseline.json"
            baseline.write_text(json.dumps({"schema_version": 1, "entries": []}), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCANNER), "--repo", "test", "--baseline", str(baseline),
                 "--json", "--fail-p2", "--files", str(production)],
                check=False, capture_output=True, text=True, cwd=root,
            )

    def test_all_static_sabotage_cases_are_blocked(self):
        for rule, source in RULE_CASES.items():
            with self.subTest(rule=rule):
                result = self.run_scanner(source)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                findings = json.loads(result.stdout)["findings"]["new_violations"]
                self.assertTrue(any(item["rule"] == rule for item in findings), findings)

    def test_isolated_test_fixture_passes(self):
        result = self.run_scanner(
            "from tests.mock_provider import provider\n", "tests/test_provider.py"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class NoCriticalFallbackBaselineTests(unittest.TestCase):
    TEST_CLASS = "BOUNDARY_CONTRACT"
    SOURCE = "import os\nDB = os.getenv('DB_TYPE', 'memory')\n"
    MODIFIED_SOURCE = "import os\nDB = os.getenv('DB_TYPE', 'mock')\n"

    def run_with_baseline(self, source: str, entries: list[dict]):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            production = root / "julia_core" / "provider.py"
            production.parent.mkdir()
            production.write_text(source, encoding="utf-8")
            baseline = root / "ncf-baseline.json"
            baseline.write_text(json.dumps({
                "schema_version": 1, "authorization": AUTHORIZATION, "entries": entries,
            }), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCANNER), "--repo", "test", "--baseline", str(baseline),
                 "--json", "--files", str(production)],
                check=False, capture_output=True, text=True, cwd=root,
            )

    def test_unchanged_debt_is_reported_but_does_not_fail(self):
        first = self.run_with_baseline(self.SOURCE, [])
        finding = json.loads(first.stdout)["findings"]["new_violations"][0]
        unchanged = self.run_with_baseline(self.SOURCE, [finding])
        self.assertEqual(unchanged.returncode, 0, unchanged.stdout + unchanged.stderr)
        self.assertEqual(json.loads(unchanged.stdout)["summary"]["EXISTING_DEBT"], 1)

    def test_modified_debt_fails(self):
        first = self.run_with_baseline(self.SOURCE, [])
        finding = json.loads(first.stdout)["findings"]["new_violations"][0]
        modified = self.run_with_baseline(self.MODIFIED_SOURCE, [finding])
        self.assertNotEqual(modified.returncode, 0, modified.stdout + modified.stderr)


if __name__ == "__main__":
    unittest.main()
