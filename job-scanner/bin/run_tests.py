"""Runs every Job Scanner suite. This is the documented verify command.

Run:
  .venv\\Scripts\\python.exe bin\\run_tests.py        (from the project root)

It exists because PowerShell 5.1 -- this project's shell -- has no `&&`, so "run these two
commands" cannot be one copy-pasteable line. Each suite keeps its own main() and its own
summary line; this only sequences them and combines the exit codes.

Add a suite by importing it and appending its main to SUITES.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_jobscan
import test_tracker

SUITES = [test_jobscan.main, test_tracker.main]


def main():
    # Run them ALL before returning. A failing matcher suite must not hide a failing
    # tracker suite -- "0 found" and "never checked" are different outcomes.
    codes = [suite() for suite in SUITES]
    failed = sum(1 for c in codes if c != 0)
    if failed:
        print("FAIL: {0} of {1} suites".format(failed, len(codes)))
        return 1
    print("OK: all {0} suites passed".format(len(codes)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
