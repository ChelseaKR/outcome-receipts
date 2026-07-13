"""Regression tests for repository-local conformance validation."""

from __future__ import annotations

from pathlib import Path

from scripts.check_conformance import waiver_failures


def test_waiver_registry_accepts_a_current_complete_entry(tmp_path: Path) -> None:
    registry = tmp_path / "waivers.yml"
    registry.write_text(
        """version: 1

waivers:
  - id: WVR-TEST
    control: SEC-10
    repo: outcome-receipts
    kind: other
    reason: deterministic test fixture
    owner: maintainer
    granted: 2099-01-01
    expires: 2099-02-01
""",
        encoding="utf-8",
    )

    assert waiver_failures(registry) == []


def test_waiver_registry_reports_schema_dates_and_duplicates(tmp_path: Path) -> None:
    registry = tmp_path / "waivers.yml"
    registry.write_text(
        """version: 2

waiverz:
  - id: WVR-TEST
    control: SEC-10
    repo: outcome-receipts
    kind: other
    reason: first fixture
    owner: maintainer
    granted: not-a-date
    expires: 2000-01-01
  - id: WVR-TEST
    control: SEC-10
    repo: outcome-receipts
    kind: other
    reason: second fixture
    owner: maintainer
    granted: 2099-02-01
    expires: 2099-01-01
""",
        encoding="utf-8",
    )

    failures = waiver_failures(registry)
    assert "waiver registry must declare version: 1" in failures
    assert "waiver registry must declare waivers" in failures
    assert "WVR-TEST: invalid granted date" in failures
    assert "WVR-TEST: expired" in failures
    assert "duplicate waiver id: WVR-TEST" in failures
    assert "WVR-TEST: expiry precedes granted date" in failures
