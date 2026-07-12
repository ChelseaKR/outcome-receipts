"""The version is single-sourced from package metadata (REL-02).

pyproject.toml is the only place a version number is written; ``__version__``
and ``receipts --version`` must both derive from it so a tagged release cannot
ship a wheel, a CLI, and a tag that disagree.
"""

from __future__ import annotations

import re
from importlib.metadata import version

import pytest

import outcome_receipts
from outcome_receipts.cli import main

# PEP 440 shape (release segment with optional pre/post/dev/local parts).
_PEP440 = re.compile(r"^\d+(\.\d+)*((a|b|rc)\d+)?(\.post\d+)?(\.dev\d+)?(\+[a-z0-9.]+)?$")


def test_dunder_version_is_the_installed_metadata_version() -> None:
    assert outcome_receipts.__version__ == version("outcome-receipts")


def test_version_is_pep440() -> None:
    assert _PEP440.match(outcome_receipts.__version__)


def test_cli_version_flag_reports_the_same_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out.strip()
    assert out == f"receipts {outcome_receipts.__version__}"
