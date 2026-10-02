import argparse
import json
import subprocess
import sys

from . import __version__
from .core import check


def main(argv=None):
    parser = argparse.ArgumentParser(description="Does your regression test catch the old bug?")
    parser.add_argument("--version", action="version", version=f"Bugbix {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("check", help="Compare selected tests on old and current code")
    run.add_argument("--repo", default=".")
    run.add_argument("--base", required=True, help="Git revision before the fix")
    run.add_argument("--head", default="working", help="working (default), or a committed revision")
    run.add_argument("--test", action="append", required=True,
                     help="Repo-relative .py file or file.py::test selector; repeatable")
    run.add_argument("--runner", choices=("unittest", "pytest"), default="unittest")
    run.add_argument("--out", required=True, help="New evidence folder outside the tested repository")
    run.add_argument("--python", default=sys.executable, help="Python interpreter with your test dependencies")
    run.add_argument("--timeout", type=float, default=30)
    run.add_argument("--repeat", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        report = check(args.repo, args.base, args.head, args.test, args.out,
                       args.python, args.timeout, args.repeat, args.runner)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"verdict": "inconclusive", "error": str(exc)}))
        return 2
    print(json.dumps({"verdict": report["verdict"], "reason": report["reason"],
                      "regression_tests": report["regression_tests"],
                      "blockers": report["blockers"][:10],
                      "blocker_count": len(report["blockers"]),
                      "report": str(args.out)}, indent=2))
    return 0 if report["verdict"] == "regression_observed" else 1
