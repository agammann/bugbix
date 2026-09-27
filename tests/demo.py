"""Produce reviewable CLI evidence using an explicitly synthetic pricing bug."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from test_product import fixture, TEST


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", required=True, help="Installed bugbix executable")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    root = Path(args.out).resolve()
    root.mkdir(parents=True, exist_ok=False)
    cases = {
        "catches-bug": (TEST, "regression_observed"),
        "weak-test": (TEST.replace("100, 20, 10), 88", "100, 0, 0), 100"), "not_demonstrated"),
        "import-error": ("import missing_demo_dependency\n" + TEST, "inconclusive"),
        "skipped": (TEST.replace("    def test_", "    @unittest.skip('not exercised')\n    def test_"), "inconclusive"),
        "timeout": ("import time\ntime.sleep(30)\n" + TEST, "inconclusive"),
    }
    summary = []
    for name, (test, expected) in cases.items():
        folder = root / name
        folder.mkdir()
        repo = fixture(folder / "repo")
        (repo / "test_pricing.py").write_text(test, encoding="utf-8")
        command = [args.cli, "check", "--repo", str(repo), "--base", "HEAD", "--test", "test_pricing.py",
                   "--out", str(folder / "evidence"), "--timeout", "0.5" if name == "timeout" else "10"]
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=60)
        (folder / "cli-stdout.json").write_text(result.stdout, encoding="utf-8")
        (folder / "cli-stderr.txt").write_text(result.stderr, encoding="utf-8")
        actual = json.loads(result.stdout)["verdict"]
        expected_exit = 0 if expected == "regression_observed" else 1
        summary.append({"case": name, "expected": expected, "actual": actual,
                        "exit_code": result.returncode,
                        "passed": actual == expected and result.returncode == expected_exit,
                        "command": command})
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if all(s["passed"] for s in summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())
