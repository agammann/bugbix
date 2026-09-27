"""Run selected pytest files and record outcomes without requiring a pytest plugin."""

import json
from pathlib import Path
import sys
import traceback


class Recorder:
    priority = {"pass": 0, "failure": 1, "skip": 2,
                "expected_failure": 2, "unexpected_success": 2, "error": 3}

    def __init__(self):
        self.events = {}
        self.error_types = {}
        self.collection_errors = []

    def record(self, nodeid, status, error_type=None):
        prior = self.events.get(nodeid, "pass")
        if self.priority[status] >= self.priority[prior]:
            self.events[nodeid] = status
            if error_type:
                self.error_types[nodeid] = error_type
            else:
                self.error_types.pop(nodeid, None)

    def pytest_collectreport(self, report):
        if report.failed:
            self.collection_errors.append(report.nodeid)

    def pytest_runtest_makereport(self, item, call):
        # This hook sees the original exception, allowing an assertion failure
        # to be distinguished from a setup/runtime error.
        import pytest

        report = pytest.TestReport.from_item_and_call(item, call)
        if report.failed:
            if hasattr(report, "wasxfail"):
                status = "unexpected_success"
            elif call.when == "call" and call.excinfo and issubclass(call.excinfo.type, AssertionError):
                status = "failure"
            else:
                status = "error"
            self.record(report.nodeid, status,
                        call.excinfo.type.__name__ if call.excinfo else None)
        elif report.skipped:
            self.record(report.nodeid, "expected_failure" if hasattr(report, "wasxfail") else "skip")
        elif call.when == "call":
            self.record(report.nodeid, "pass")
        return report


def main():
    root = Path.cwd()
    target = Path(sys.argv[1])
    paths = sys.argv[2:]
    sys.path[0:0] = [str(root), str(root / "src")]
    try:
        import pytest

        recorder = Recorder()
        exit_code = int(pytest.main(["-q", "-p", "no:cacheprovider", *paths], plugins=[recorder]))
        payload = {"events": [{"id": nodeid, "status": status,
                               **({"error_type": recorder.error_types[nodeid]}
                                  if nodeid in recorder.error_types else {})}
                              for nodeid, status in sorted(recorder.events.items())],
                   "tests_run": len(recorder.events),
                   "runner_error": (f"Collection failed: {recorder.collection_errors}"
                                    if recorder.collection_errors else None)}
        if exit_code not in (0, 1) and not payload["runner_error"]:
            payload["runner_error"] = f"pytest exited {exit_code}"
    except BaseException:
        traceback.print_exc()
        payload = {"events": [], "tests_run": 0, "runner_error": traceback.format_exc()}
        exit_code = 2
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
