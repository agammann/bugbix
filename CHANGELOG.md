# Changelog

## 0.4.0a1 — public alpha

- Compare selected unittest or pytest cases on a Git baseline and a committed or working-tree fix.
- Run each side twice by default and save source snapshots, hashes, structured outcomes, and raw logs.
- Reject weak tests that pass on old code, setup errors, skipped tests, changed inputs, and test-only changes.
- Show a short actionable cause for runner errors while retaining the full trace.
- Validate the packaged command on merged public fixes in boltons and more-itertools; document the humanize build-setup limit.

The alpha is focused on Python projects with a known pre-fix commit. See
[VERIFICATION.md](VERIFICATION.md) for observed results and limits.
