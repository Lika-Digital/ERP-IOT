"""Read a pytest JUnit XML report and decide if the run is a real pass (TC-ERP-BOOT-02).

A pytest exit code of 0 is not enough: 0 tests collected, or tests that
skipped themselves because something was not running, also give 0. That is
exactly how a gate passes empty. Here:

  - collected == 0          -> fail
  - skipped   > 0           -> fail, and every skipped test is named
  - failures or errors > 0  -> fail

Prints one line `PYTEST: collected=N passed=N skipped=N failed=N errors=N`.
Usage: python scripts/pytest_counts.py <junit.xml>
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET  # noqa: S405 — our own pytest output, not untrusted


def main(path: str) -> int:
    try:
        root = ET.parse(path).getroot()  # noqa: S314
    except (OSError, ET.ParseError) as exc:
        print(f"PYTEST: no readable report ({exc}) - counting as failure")
        return 1

    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    total = sum(int(s.get("tests", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    failures = sum(int(s.get("failures", 0)) for s in suites)
    errors = sum(int(s.get("errors", 0)) for s in suites)
    passed = total - skipped - failures - errors

    print(f"PYTEST: collected={total} passed={passed} skipped={skipped} "
          f"failed={failures} errors={errors}")

    bad = False
    if total == 0:
        print("  no tests collected - an empty run is not a pass")
        bad = True
    if skipped:
        print("  skipped tests are not allowed in the gate:")
        for case in root.iter("testcase"):
            if case.find("skipped") is not None:
                print(f"    - {case.get('classname')}::{case.get('name')}")
        bad = True
    if failures or errors:
        bad = True
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
