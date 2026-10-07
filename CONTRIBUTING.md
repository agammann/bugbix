# Contributing

Bugbix is a Python command-line tool for bounded regression evidence. Focused bug reports and
small changes that improve its stated use case are welcome.

Before opening an issue, include the Bugbix version, Python and Git versions,
OS, the command you ran, the verdict, and the relevant blocker or error. A
minimal public repository is useful when the failure depends on Git state.
Review evidence folders before attaching them: they contain copied source and
raw test output, which may include private paths or other sensitive data.

For code changes:

1. Run `python -m pip install pytest==9.1.1 build==1.6.1` in a disposable environment.
2. Run `python -m unittest discover -s tests -v`.
3. Add a test for a changed verdict or runner behavior when it protects against
   a concrete failure.
4. Keep the failure and success states reproducible and distinguish observed
   results from assumptions in the pull request.

The current scope is selected Python unittest and pytest tests against a known
pre-fix Git commit. Discuss broader runner or language support before building
it.

## Build and verify the delivered artifacts

```sh
python scripts/package.py
python scripts/consumer.py --out ../bugbix-consumer-check
```

Choose a new consumer directory outside the source checkout. Packaging verifies runtime source bytes, CLI entry point, version, MIT license and archive contents, then writes the wheel/source archive and checksums under ignored `artifacts/`. The consumer installs each actual artifact in its own fresh virtual environment, exercises the installed CLI outside source, verifies positive/negative verdicts and exit codes, preserves the dirty fixture checkout, and tests recovery into a new output directory. Reports remain in the consumer directory.

The workflow retains Windows/Linux and Python 3.11/3.12 checks. Pull requests and manual dispatches have read-only permissions. Main pushes publish only after all four lanes pass, using the same-run verified wheel/source artifact. The publisher checks the exact five-file package/checksum set, current main/tag commit, matching draft, and complete uploaded digests/sizes before publishing. Published versions remain unchanged; same-commit draft retries can resume.

Follow the [v1 contract](docs/stability.md). Add concrete regression coverage for changes to engine behavior; documentation/version packaging changes need actual installation checks rather than duplicate engine tests.
