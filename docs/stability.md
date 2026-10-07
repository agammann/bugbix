# Bugbix v1 stability contract

Version 1.0.0 supports selected Python unittest or pytest cases against a known pre-fix Git commit and a current working tree or committed fix. Python 3.11+ and Git are required. The installed runtime has no package dependencies, account, model API or network service. Pytest and the tested project's dependencies belong in the interpreter selected by `--python`; Bugbix does not install them.

Within v1, `bugbix check` and the documented options (`--repo`, `--base`, `--head`, repeated `--test`, `--runner`, `--out`, `--python`, `--timeout`, `--repeat`) remain supported. Defaults remain working-tree head, unittest, two repetitions and 30 seconds per run. `--version` prints `Bugbix <version>` and exits 0. Help exits 0. Command syntax errors use argparse diagnostics on stderr and exit 2.

A parsed check prints JSON to stdout. Exit 0 means `regression_observed`; exit 1 means another completed verdict (`not_demonstrated`, `fix_fails`, `inconclusive`, `unstable`). Configuration, snapshot or orchestration errors exit 2 and include a JSON error. A failure-to-pass transition needs matching assertion outcomes, passing current tests and a non-test source change. Errors, skips, expected failures, unexpected passes, missing results, timeouts and input mutation prevent a qualifying regression. Repeated disagreement produces `unstable`.

Written `report.json` retains `schema_version: 2`. Verdict names and the documented top-level data remain supported within v1; readers should allow additional fields. Reports include source snapshots/hashes, selected tests, revisions, runs, blockers and limits. Timing, temporary paths, human-readable reason strings, raw traces and Markdown layout are observational output rather than machine parsing contracts. Old evidence is retained as produced; the CLI does not rewrite or migrate existing report folders.

Snapshot operations leave the original checkout, branch and index intact. Evidence is written to a new directory outside that repository; existing output folders are refused. Only selected current test files are transplanted onto the baseline, so shared fixtures/helpers must already work there. The documented file/size limits and rejection of submodules, symlinks and Git LFS pointers remain part of the supported scope. Tests execute with the caller's permissions and inherited dependencies; snapshots are not an execution sandbox or a hermetic environment.

Windows and Linux on Python 3.11/3.12 are the CI lanes. Local release checks use Windows Python 3.12.14 and pytest 9.1.1. Other interpreter versions/platforms, languages, arbitrary pytest plugins, detached background processes and full-suite/bug-relevance guarantees require separate evidence.

## Upgrade from 0.4.0a2

Install the v1 wheel or source archive in your environment and check `bugbix --version`. The check options, verdicts, exit codes and report schema 2 are unchanged. Keep older evidence folders for comparison; use a new output directory for every v1 run. No repository migration, service registration or account change is needed. Follow [recovery and removal](recovery.md) for interrupted/inconclusive runs and uninstalling the CLI.
