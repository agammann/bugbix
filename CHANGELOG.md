# Changelog

## 1.0.0

2026-10-06

- Establish the v1 CLI, verdict/exit and report schema 2 stability contract for selected Python regression checks.
- Retain the verified unittest/pytest engine, final xfail/xpass handling and original-checkout preservation behavior.
- Deliver a prebuilt wheel and installable source archive with MIT licensing and SHA256 checksums.
- Verify both actual artifacts in fresh environments, including positive/negative verdicts, recovery and checkout preservation.
- Gate main-branch release publication on the existing Windows/Linux and Python 3.11/3.12 checks and complete artifact verification.

## 0.4.0a2 — pytest outcome correction

- Record final pytest outcomes after expected-failure processing; mixed suites containing xfail or xpass remain inconclusive.
- Preserve ordinary assertion failures, runtime errors, and existing unittest behavior.
- Align the package, CLI, and report version.

## 0.4.0a1 — public alpha

- Compare selected unittest or pytest cases on a Git baseline and a committed or working-tree fix.
- Run each side twice by default and save source snapshots, hashes, structured outcomes, and raw logs.
- Reject weak tests that pass on old code, setup errors, skipped tests, changed inputs, and test-only changes.
- Show a short actionable cause for runner errors while retaining the full trace.
- Validate the packaged command on merged public fixes in boltons and more-itertools; document the humanize build-setup limit.

The alpha is focused on Python projects with a known pre-fix commit. See
[VERIFICATION.md](VERIFICATION.md) for observed results and limits.
