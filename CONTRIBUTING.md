# Contributing

Bugbix is an experimental Python command-line tool. Focused bug reports and
small changes that improve its stated use case are welcome.

Before opening an issue, include the Bugbix version, Python and Git versions,
OS, the command you ran, the verdict, and the relevant blocker or error. A
minimal public repository is useful when the failure depends on Git state.
Review evidence folders before attaching them: they contain copied source and
raw test output, which may include private paths or other sensitive data.

For code changes:

1. Run `python -m pip install pytest` in a disposable environment.
2. Run `python -m unittest discover -s tests -v`.
3. Add a test for a changed verdict or runner behavior when it protects against
   a concrete failure.
4. Keep the failure and success states reproducible and distinguish observed
   results from assumptions in the pull request.

The current scope is selected Python unittest and pytest tests against a known
pre-fix Git commit. Discuss broader runner or language support before building
it.
