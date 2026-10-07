# Recover a check and remove Bugbix

A completed `inconclusive` result has evidence. Read its blockers and the linked stdout/stderr before changing the test environment. A missing dependency, shared fixture, skipped/xfail case or runner error must be resolved in the selected interpreter or test selection. Keep the original report, correct the cause, and run again with a new `--out` directory. An existing output folder is refused with exit 2 and remains untouched.

For an interruption or orchestration failure, a partial evidence directory may lack a complete report. Retain it while investigating; it is not a completed verdict. Stop the interrupted test processes if necessary, check the original repository state, and rerun into a new directory. Bugbix's normal timeout handling stops the main test process tree. Intentionally detached processes remain outside the supported scope.

`--base` must identify the real pre-fix commit. If HEAD already includes the fix, choose an older saved commit. Bugbix cannot restore unsaved pre-fix working-tree state. Snapshot operations preserve the original checkout; tests themselves run with your permissions and can access paths/services outside their copied source. Use trusted code and review evidence before sharing it.

Reports contain source copies and raw output. Retention and sharing are your responsibility. You may archive a complete evidence directory as a unit; its Markdown links refer to the adjacent per-run directories. Removing an evidence directory does not change the tested checkout. Verify its absolute path before removing anything.

To remove the installed package, use its environment's interpreter:

```sh
python -m pip uninstall bugbix
```

An isolated virtual environment can be removed after preserving any evidence saved inside it. Bugbix has no account, daemon, scheduled task, telemetry or hosted resource to remove. Existing Git repositories and saved evidence remain independently usable.
