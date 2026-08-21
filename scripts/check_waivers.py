#!/usr/bin/env python3
"""Fail closed when a repository waiver registry is malformed or expired."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from check_conformance import _load_control_ids, waiver_failures


def main() -> int:
    """Validate the requested registry and report every failure."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    parser.add_argument(
        "--standards-dir",
        type=Path,
        default=None,
        help="path to a checked-out ChelseaKR/portfolio-standards; when given, waiver "
        "control IDs are validated against its controls.yml instead of format-checked only",
    )
    args = parser.parse_args()

    control_ids = _load_control_ids(args.standards_dir) if args.standards_dir is not None else None
    failures = waiver_failures(args.registry, control_ids=control_ids)
    if failures:
        print("waiver validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"waiver validation: pass ({args.registry})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
