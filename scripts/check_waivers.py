#!/usr/bin/env python3
"""Fail closed when a repository waiver registry is malformed or expired."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from check_conformance import waiver_failures


def main() -> int:
    """Validate the requested registry and report every failure."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    args = parser.parse_args()

    failures = waiver_failures(args.registry)
    if failures:
        print("waiver validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"waiver validation: pass ({args.registry})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
