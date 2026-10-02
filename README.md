# Bugbix

**Does the regression test catch the bug before your fix?**

[![Verify Bugbix](https://github.com/agammann/bugbix/actions/workflows/verify.yml/badge.svg)](https://github.com/agammann/bugbix/actions/workflows/verify.yml)

Bugbix gives coding agents and reviewers a local check for that question.
It runs the same selected Python tests against a Git baseline and your current
code, including uncommitted edits and new, non-ignored files. It records individual
test outcomes, source hashes, snapshots, and raw logs.

Version 0.4.0a2 is a public alpha for Python projects with a known pre-fix Git
commit. It has no runtime package dependencies, account, or model API. It has
been tested locally on Windows with Python 3.12; see [VERIFICATION.md](VERIFICATION.md)
for the exact results and current limits.

## Install

Requires Python 3.11+ and Git. Install the alpha from its tagged source:

```sh
python -m pip install "git+https://github.com/agammann/bugbix.git@v0.4.0-alpha.2"
bugbix --version
```

Alternatively, download the wheel from the [alpha release](https://github.com/agammann/bugbix/releases/tag/v0.4.0-alpha.2)
and install that file with `python -m pip install /path/to/bugbix-0.4.0a2-py3-none-any.whl`.
Bugbix is not published to PyPI.

## Quick start

After making a fix and adding a regression test, run:

```sh
bugbix check --repo /path/to/project --base HEAD --test tests/test_bug.py --out /path/to/evidence/run-001
```

`--base HEAD` is the pre-fix commit when the fix is still in your working tree.
The command returns JSON and writes a readable `report.md` plus raw logs. For
example, a qualifying transition returns `regression_observed`; a test that
already passes on the old code returns `not_demonstrated`.

For pytest functions or fixtures, add `--runner pytest` and pass `--python` with
pytest and the project's test dependencies installed:

```sh
bugbix check --repo /path/to/project --base HEAD --test tests/test_bug.py --runner pytest --python /path/to/venv/python --out /path/to/evidence/run-002
```

Windows PowerShell example:

```powershell
bugbix check --repo C:\code\project --base HEAD --test tests/test_bug.py --out C:\evidence\run-001
```

Use a new output folder **outside** the tested repository. Test paths use `/`,
are relative to the repository root. The default runner needs `unittest.TestCase`
tests; the pytest runner accepts pytest tests and fixtures.
Repeat `--test` to select more files. No commit is needed for the fix or new tests.

To isolate one test in a file, append `::` and its selector. A unittest selector
uses `ClassName.test_method`; a pytest selector uses its normal node ID suffix:

```sh
bugbix check --repo /path/to/project --base HEAD --test tests/test_bug.py::BugTests.test_case --out /path/to/evidence/focused
bugbix check --repo /path/to/project --base HEAD --runner pytest --test tests/test_bug.py::test_case --python /path/to/venv/python --out /path/to/evidence/pytest-focused
```

If the fix is committed, select the two revisions:

```sh
bugbix check --repo /path/to/project --base HEAD~1 --head HEAD --test tests/test_bug.py --out /path/to/evidence/run-002
```

Pass `--python /path/to/venv/python` to use an environment with your test
dependencies. Bugbix does not install repository dependencies. Both versions
use that same interpreter and installed dependencies; imports search the copied
repository root and its `src/` directory first.

## Results

| Verdict | Meaning |
| --- | --- |
| `regression_observed` | At least one matching test fails by assertion on old code; all selected tests pass on current code, consistently across repetitions. |
| `not_demonstrated` | The tests already pass on old code. They do not demonstrate this regression. |
| `fix_fails` | Current code still fails a selected assertion. |
| `inconclusive` | Errors, skips, zero tests, missing results, timeout, changed test identities, or input mutation prevent a conclusion. |
| `unstable` | Repeated runs produced different outcomes. |

Exit `0` means `regression_observed`; exit `1` means another completed verdict;
exit `2` means configuration, snapshot, or orchestration failure. CLI output is JSON.
For `inconclusive`, the CLI and report name the blocking run, test, and exception
type when available. Runner failures include a short cause; the full trace remains
in the evidence folder. An assertion failure in one test does not override an error,
skip, expected failure (`xfail`), or unexpected pass (`xpass`) in another selected
test. Remove an obsolete expected-failure marker when checking a fixed test. Select the relevant test and rerun, or
repair the test error. The report lists Git-visible changed files and links both stdout
and stderr. A failure-to-pass transition cannot be reported as a regression when
the only Git-visible changes are test files. Test-file recognition uses common
Python names and `test/` or `tests/` folders; review the changed-file list.

Each evidence folder contains `report.md`, `report.json`, and per-run snapshots,
stdout, stderr, and structured test results. Default: two runs per version, a
30-second timeout per run. Configure `--repeat` (1–10) and `--timeout` (up to 3600).

## How it works

1. Read the chosen baseline directly from Git blobs.
2. Capture current tracked and non-ignored untracked files, or a chosen commit.
3. Copy exactly the selected current test files over the baseline snapshot.
4. Run each version in fresh directories and Python processes.
5. Compare matching test identities and preserve the evidence.

Git branch, index, and working files are not changed by Bugbix's snapshot
operations. Only selected test files are transplanted: shared fixtures or helpers
must already work on the baseline. A missing helper produces `inconclusive`.

## Scope and limits

- This alpha supports selected Python test files or individual cases with unittest or pytest.
  Other languages and runners are not supported. Package-relative test imports
  and project-specific pytest plugins may require additional setup.
- `--base` must be a real pre-fix commit. If `HEAD` already contains some or all
  of the fix, choose an older commit. Bugbix cannot reconstruct uncommitted
  work that existed before the fix unless it was saved elsewhere.
- A failure-to-pass transition is evidence of a behavior difference. Review the
  assertion and failure trace to establish that it is the intended bug. This
  does not verify the full suite, user requirements, or overall correctness.
- Tests and their imports execute with your user permissions and inherited
  environment. Snapshot directories are not a security sandbox. Tests can reach
  services, credentials, and paths outside their directory. Use trusted code.
- Only committed baseline contents are captured. Submodules, symlinks, and Git
  LFS pointers are rejected. Limit: 5,000 files, 10 MiB per file, 100 MiB total.
- Working-tree capture is not an atomic filesystem snapshot. Avoid concurrent
  edits during capture. Source hashes describe the captured bytes.
- Installed dependencies, external services, environment variables, and clocks
  are not frozen. Local packages already installed in the selected environment
  can affect imports. This release does not create a hermetic environment.
- Files supplied to a run are compared afterward. A test that changes and
  restores a file can evade this check. Results are not signed or resistant to
  intentional fabrication by code running with the same permissions.
- The runner bounds the main test process and kills its process tree on timeout.
  Tests that intentionally detach background processes are unsupported.
- Evidence contains copied source and raw test output; inspect it before sharing.
  Reports remain local; Bugbix performs no network requests itself.

## Run the product tests

```sh
python -m pip install pytest
python -m unittest discover -s tests -v
```

See [VERIFICATION.md](VERIFICATION.md) for observed results, [DIRECTION.md](DIRECTION.md)
for the product scope and alternatives, [CHANGELOG.md](CHANGELOG.md) for release
changes, and [CONTRIBUTING.md](CONTRIBUTING.md) for bug reports and contributions.
