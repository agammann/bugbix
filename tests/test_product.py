import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from bugbix.core import check, classify, error_summary, git


TEST = '''import unittest
from pricing import total

class PricingTests(unittest.TestCase):
    def test_discount_applies_before_tax(self):
        self.assertEqual(total(100, 20, 10), 88)
'''
OLD = "def total(price, discount, tax):\n    return price * (100 + tax) // 100 - discount\n"
FIX = "def total(price, discount, tax):\n    return (price - discount) * (100 + tax) // 100\n"


def fixture(path):
    path.mkdir()
    git(path, "init", "--quiet")
    (path / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    (path / "pricing.py").write_text(OLD, encoding="utf-8")
    git(path, "add", ".")
    git(path, "-c", "user.name=Bugbix test", "-c", "user.email=test@example.invalid",
        "commit", "--quiet", "-m", "Baseline fixture")
    (path / "pricing.py").write_text(FIX, encoding="utf-8")
    (path / "test_pricing.py").write_text(TEST, encoding="utf-8")
    return path


class ProductTests(unittest.TestCase):
    def test_error_summary_strips_terminal_codes(self):
        self.assertEqual(error_summary("ModuleNotFoundError: missing\x1b[0m"),
                         "ModuleNotFoundError: missing")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bugbix-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = fixture(self.root / "repo")

    def run_check(self, **kwargs):
        return check(self.repo, "HEAD", "working", ["test_pricing.py"],
                     self.root / "evidence", repeat=kwargs.pop("repeat", 1), **kwargs)

    def change_test(self, content):
        (self.repo / "test_pricing.py").write_text(content, encoding="utf-8")

    def test_real_regression_and_repository_preserved(self):
        before = git(self.repo, "status", "--porcelain=v1", raw=True)
        content = (self.repo / "pricing.py").read_bytes()
        report = self.run_check(repeat=2)
        self.assertEqual(report["verdict"], "regression_observed")
        self.assertEqual(len(report["regression_tests"]), 1)
        self.assertEqual(report["runs"]["base"][0]["exit_code"], 1)
        self.assertEqual(report["runs"]["head"][0]["exit_code"], 0)
        self.assertEqual(before, git(self.repo, "status", "--porcelain=v1", raw=True))
        self.assertEqual(content, (self.repo / "pricing.py").read_bytes())
        self.assertTrue((self.root / "evidence/report.md").is_file())

    def test_test_that_passes_before_fix_is_rejected(self):
        self.change_test(TEST.replace("100, 20, 10), 88", "100, 0, 0), 100"))
        self.assertEqual(self.run_check()["verdict"], "not_demonstrated")

    def test_identical_captured_inputs_cannot_prove_a_regression(self):
        (self.repo / "pricing.py").write_text(OLD, encoding="utf-8")
        self.change_test("import unittest\nfrom pathlib import Path\n"
                         "class LocationTest(unittest.TestCase):\n"
                         "    def test_side(self):\n"
                         "        self.assertTrue(Path.cwd().parent.name.startswith('head-'))\n")
        (self.repo / "test_unrelated.py").write_text("def test_placeholder():\n    assert True\n",
                                                     encoding="utf-8")
        report = self.run_check()
        self.assertEqual(report["verdict"], "inconclusive")
        self.assertIn("no_non_test_changes", [item["issue"] for item in report["blockers"]])
        self.assertEqual(report["changed_files"], ["test_pricing.py", "test_unrelated.py"])

    def test_broken_fix_is_rejected(self):
        (self.repo / "pricing.py").write_text(OLD, encoding="utf-8")
        self.assertEqual(self.run_check()["verdict"], "fix_fails")

    def test_import_failure_is_not_a_regression(self):
        self.change_test("import a_module_that_does_not_exist\n" + TEST)
        report = self.run_check()
        self.assertEqual(report["verdict"], "inconclusive")
        self.assertTrue(any("a_module_that_does_not_exist" in item.get("detail", "")
                            for item in report["blockers"]))
        markdown = (self.root / "evidence/report.md").read_text(encoding="utf-8")
        self.assertIn("a_module_that_does_not_exist", markdown)

    def test_skips_are_inconclusive(self):
        self.change_test(TEST.replace("    def test_", "    @unittest.skip('not exercised')\n    def test_"))
        self.assertEqual(self.run_check()["verdict"], "inconclusive")

    def test_zero_tests_are_inconclusive(self):
        self.change_test("x = 1\n")
        self.assertEqual(self.run_check()["verdict"], "inconclusive")

    def test_test_errors_are_inconclusive(self):
        self.change_test(TEST.replace("self.assertEqual(total(100, 20, 10), 88)", "raise RuntimeError('setup unavailable')"))
        self.assertEqual(self.run_check()["verdict"], "inconclusive")

    def test_one_error_explains_inconclusive_mixed_suite(self):
        self.change_test(TEST + "\nclass Other(unittest.TestCase):\n"
                         "    def test_keyerror_on_old_code(self):\n"
                         "        if total(100, 20, 10) != 88:\n"
                         "            {}['missing']\n")
        report = self.run_check()
        self.assertEqual(report["verdict"], "inconclusive")
        self.assertTrue(any(item.get("error_type") == "KeyError" and
                            "test_keyerror_on_old_code" in item.get("test", "")
                            for item in report["blockers"]))
        markdown = (self.root / "evidence/report.md").read_text(encoding="utf-8")
        self.assertIn("KeyError", markdown)
        self.assertIn("[stdout](base-1/stdout.txt)", markdown)
        focused = check(self.repo, "HEAD", "working",
                        ["test_pricing.py::PricingTests.test_discount_applies_before_tax"],
                        self.root / "focused", repeat=1)
        self.assertEqual(focused["verdict"], "regression_observed")

    def test_timeout_is_inconclusive(self):
        self.change_test("import time\ntime.sleep(30)\n" + TEST)
        report = self.run_check(timeout=0.2)
        self.assertEqual(report["verdict"], "inconclusive")
        self.assertEqual(report["runs"]["base"][0]["status"], "timeout")

    def test_input_mutation_is_inconclusive(self):
        self.change_test(TEST + "\nfrom pathlib import Path\nPath('pricing.py').write_text('changed')\n")
        self.assertEqual(self.run_check()["verdict"], "inconclusive")

    def test_subtest_failures_are_recorded(self):
        self.change_test(TEST.replace("        self.assertEqual", "        with self.subTest(case='discount'):\n            self.assertEqual"))
        self.assertEqual(self.run_check()["verdict"], "regression_observed")

    def test_output_inside_repository_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            check(self.repo, "HEAD", "working", ["test_pricing.py"], self.repo / "evidence")

    def test_snapshot_does_not_honor_export_ignore(self):
        (self.repo / ".gitattributes").write_text("pricing.py export-ignore\n", encoding="utf-8")
        git(self.repo, "add", ".gitattributes")
        git(self.repo, "-c", "user.name=Bugbix test", "-c", "user.email=test@example.invalid",
            "commit", "--quiet", "-m", "Archive attribute")
        self.assertEqual(self.run_check()["verdict"], "regression_observed")

    def test_installed_style_cli_json_and_exit_codes(self):
        package = Path(__file__).resolve().parents[1]
        p = subprocess.run([sys.executable, "-m", "bugbix", "check", "--repo", str(self.repo),
                            "--base", "HEAD", "--test", "test_pricing.py", "--repeat", "1",
                            "--out", str(self.root / "cli-evidence")], cwd=package,
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertEqual(json.loads(p.stdout)["verdict"], "regression_observed")

    def test_repetition_disagreement_is_unstable(self):
        report = self.run_check()
        other = json.loads(json.dumps(report["runs"]["base"][0]))
        other["exit_code"] = 0
        other["result"]["events"][0]["status"] = "pass"
        verdict, _, _ = classify(report["runs"]["base"] + [other], report["runs"]["head"] * 2)
        self.assertEqual(verdict, "unstable")

    def test_pytest_function_catches_dirty_tree_fix(self):
        try:
            import pytest  # noqa: F401
        except ImportError:
            self.skipTest("pytest is not installed in this test environment")
        self.change_test("from pricing import total\n\ndef test_discount():\n    assert total(100, 20, 10) == 88\n")
        report = self.run_check(runner="pytest")
        self.assertEqual(report["verdict"], "regression_observed", report["reason"])
        self.assertEqual(report["regression_tests"], ["test_pricing.py::test_discount"])
        focused = check(self.repo, "HEAD", "working", ["test_pricing.py::test_discount"],
                        self.root / "focused", repeat=1, runner="pytest")
        self.assertEqual(focused["verdict"], "regression_observed")

    def test_pytest_xfail_outcomes_block_mixed_regression(self):
        try:
            import pytest  # noqa: F401
        except ImportError:
            self.skipTest("pytest is not installed in this test environment")
        self.change_test("import pytest\nfrom pricing import total\n"
                         "def test_discount():\n    assert total(100, 20, 10) == 88\n"
                         "@pytest.mark.xfail(reason='pending', strict=False)\n"
                         "def test_marked():\n    assert total(100, 20, 10) == 88\n")
        report = self.run_check(runner="pytest")
        self.assertEqual(report["verdict"], "inconclusive")
        outcomes = {(item["run"], item.get("status")) for item in report["blockers"]}
        self.assertIn(("base-1", "expected_failure"), outcomes)
        self.assertIn(("head-1", "unexpected_success"), outcomes)

    def test_pytest_xpass_does_not_count_as_an_ordinary_pass(self):
        try:
            import pytest  # noqa: F401
        except ImportError:
            self.skipTest("pytest is not installed in this test environment")
        for strict in (False, True):
            with self.subTest(strict=strict):
                self.change_test("import pytest\n"
                                 f"@pytest.mark.xfail(reason='pending', strict={strict})\n"
                                 "def test_marked():\n    assert True\n")
                report = check(self.repo, "HEAD", "working", ["test_pricing.py"],
                               self.root / f"xpass-{strict}", repeat=1, runner="pytest")
                self.assertEqual(report["verdict"], "inconclusive")

    def test_pytest_runtime_error_is_inconclusive(self):
        try:
            import pytest  # noqa: F401
        except ImportError:
            self.skipTest("pytest is not installed in this test environment")
        self.change_test("def test_broken():\n    raise RuntimeError('not an assertion')\n")
        self.assertEqual(self.run_check(runner="pytest")["verdict"], "inconclusive")

    def test_pytest_collection_error_names_missing_module(self):
        try:
            import pytest  # noqa: F401
        except ImportError:
            self.skipTest("pytest is not installed in this test environment")
        self.change_test("import a_module_that_does_not_exist\n\ndef test_case():\n    assert True\n")
        report = self.run_check(runner="pytest")
        self.assertEqual(report["verdict"], "inconclusive")
        self.assertTrue(any("a_module_that_does_not_exist" in item.get("detail", "")
                            for item in report["blockers"]))


if __name__ == "__main__":
    unittest.main()
