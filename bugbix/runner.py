"""Executed in a fresh interpreter; record unittest outcomes structurally."""

import importlib.util
import json
from pathlib import Path
import sys
import traceback
import unittest


class Result(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.events = []

    def event(self, test, status, error_type=None):
        event = {"id": test.id(), "status": status}
        if error_type:
            event["error_type"] = error_type
        self.events.append(event)

    def addSuccess(self, test):
        super().addSuccess(test)
        self.event(test, "pass")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.event(test, "failure", err[0].__name__)

    def addError(self, test, err):
        super().addError(test, err)
        self.event(test, "error", err[0].__name__)

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.event(test, "skip")

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.event(test, "expected_failure")

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.event(test, "unexpected_success")

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err:
            self.event(test, "failure" if issubclass(err[0], test.failureException) else "error",
                       err[0].__name__)


def main():
    root = Path.cwd()
    target = Path(sys.argv[1])
    paths = sys.argv[2:]
    # -I removes inherited PYTHONPATH and cwd. Add only the tested source here.
    sys.path[0:0] = [str(root), str(root / "src")]
    try:
        suite = unittest.TestSuite()
        for index, selection in enumerate(paths):
            name, _, node = selection.partition("::")
            spec = importlib.util.spec_from_file_location(f"bugbix_test_{index}", root / name)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            if node:
                suite.addTests(unittest.defaultTestLoader.loadTestsFromName(f"{spec.name}.{node}"))
            else:
                suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(suite)
        payload = {"events": result.events, "tests_run": result.testsRun,
                   "runner_error": None}
        status = 0 if result.wasSuccessful() else 1
    except BaseException:
        traceback.print_exc()
        payload = {"events": [], "tests_run": 0, "runner_error": traceback.format_exc()}
        status = 2
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
