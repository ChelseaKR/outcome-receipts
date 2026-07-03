"""Tests for multi-funder template reuse.

One run computes the figure set once and renders it into more than one named
funder template format. Each format is held to the same grounding gate and written
to its own output subdirectory; the shared figures make each subdir's receipts
figure set identical. A legacy single-template spec is unchanged, and an unbound
number in any one template fails the whole export closed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from outcome_receipts.cli import main
from outcome_receipts.config import load_spec
from outcome_receipts.models import ReportSpec, TemplateSpec

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _receipts_figures(manifest_path: Path) -> list[dict[str, object]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    figures: list[dict[str, object]] = payload["receipts"]
    return figures


def _multi_template_spec(tmp_path: Path, second_template: str) -> Path:
    """A minimal two-template spec over a one-row data file."""

    (tmp_path / "data.csv").write_text("client_id\nC001\n", encoding="utf-8")
    spec = tmp_path / "report.toml"
    spec.write_text(
        '[data]\npath = "data.csv"\n'
        '[report]\ntitle = "Shared"\n'
        '[[report.templates]]\nid = "funder-a"\ntemplate = "served {clients}"\n'
        f'[[report.templates]]\nid = "funder-b"\ntemplate = "{second_template}"\n'
        '[metrics.clients]\nvalue_sql = "SELECT COUNT(*) FROM data"\n'
        'slice_sql = "SELECT * FROM data"\n',
        encoding="utf-8",
    )
    return spec


# (a) config parsing of [[report.templates]] produces multiple TemplateSpecs.


def test_load_spec_parses_multiple_templates() -> None:
    spec = load_spec(EXAMPLES / "multi-funder" / "report.toml")
    assert spec.report.template == ""  # legacy single template is unset
    ids = [t.template_id for t in spec.report.templates]
    assert ids == ["funder-a", "funder-b"]
    a, b = spec.report.templates
    assert a.title == "Housing Outcomes — Funder A Summary"
    assert b.title == "Housing Program Report — Funder B"
    # effective_templates returns the declared formats verbatim when present.
    assert spec.report.effective_templates == spec.report.templates


def test_template_title_defaults_to_report_title(tmp_path: Path) -> None:
    spec_path = tmp_path / "report.toml"
    (tmp_path / "data.csv").write_text("client_id\nC001\n", encoding="utf-8")
    spec_path.write_text(
        '[data]\npath = "data.csv"\n'
        '[report]\ntitle = "Fallback"\n'
        '[[report.templates]]\nid = "t"\ntemplate = "n {clients}"\n'
        '[metrics.clients]\nvalue_sql = "SELECT COUNT(*) FROM data"\n'
        'slice_sql = "SELECT * FROM data"\n',
        encoding="utf-8",
    )
    spec = load_spec(spec_path)
    [template] = spec.report.templates
    assert template.title == "Fallback"


def test_template_entry_requires_id_and_template(tmp_path: Path) -> None:
    spec_path = tmp_path / "report.toml"
    (tmp_path / "data.csv").write_text("client_id\nC001\n", encoding="utf-8")
    spec_path.write_text(
        '[data]\npath = "data.csv"\n[report]\ntitle = "x"\n'
        '[[report.templates]]\nid = "t"\n'  # no template
        '[metrics.clients]\nvalue_sql = "SELECT COUNT(*) FROM data"\n'
        'slice_sql = "SELECT * FROM data"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="templates"):
        load_spec(spec_path)


def test_spec_without_template_or_templates_is_rejected(tmp_path: Path) -> None:
    spec_path = tmp_path / "report.toml"
    (tmp_path / "data.csv").write_text("client_id\nC001\n", encoding="utf-8")
    spec_path.write_text(
        '[data]\npath = "data.csv"\n[report]\ntitle = "x"\n'
        '[metrics.clients]\nvalue_sql = "SELECT COUNT(*) FROM data"\n'
        'slice_sql = "SELECT * FROM data"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="template"):
        load_spec(spec_path)


# (b) a run produces one report per template with identical receipts figure sets.


def test_run_writes_one_subdir_per_template_with_shared_figures(tmp_path: Path) -> None:
    out = tmp_path / "out"
    code = main(
        ["run", "--config", str(EXAMPLES / "multi-funder" / "report.toml"),
         "--out", str(out), "--reproducible"]
    )
    assert code == 0
    a_dir = out / "funder-a"
    b_dir = out / "funder-b"
    for sub in (a_dir, b_dir):
        assert (sub / "report.md").exists()
        assert (sub / "receipts.json").exists()
        assert (sub / "trace.html").exists()
    # The shared figure set is byte-identical across the two funder formats.
    assert _receipts_figures(a_dir / "receipts.json") == _receipts_figures(
        b_dir / "receipts.json"
    )
    # The narratives differ (terse vs fuller), each headed by its own title.
    assert a_dir.joinpath("report.md").read_text(encoding="utf-8") != b_dir.joinpath(
        "report.md"
    ).read_text(encoding="utf-8")
    assert "Funder A Summary" in (a_dir / "report.md").read_text(encoding="utf-8")


# (c) a legacy single-template spec still works unchanged (flat output layout).


def test_legacy_single_template_writes_flat_layout(tmp_path: Path) -> None:
    out = tmp_path / "out"
    code = main(
        ["run", "--config", str(EXAMPLES / "housing-demo" / "report.toml"),
         "--out", str(out), "--reproducible"]
    )
    assert code == 0
    # No per-template subdir: the files sit directly in the output dir.
    assert (out / "report.md").exists()
    assert (out / "receipts.json").exists()
    assert (out / "trace.html").exists()
    assert not (out / "report").exists()


def test_legacy_spec_effective_template_is_synthesized() -> None:
    spec = ReportSpec(title="Legacy", template="served {clients}")
    assert spec.templates == ()
    [only] = spec.effective_templates
    assert only == TemplateSpec(
        template_id="report", title="Legacy", template="served {clients}"
    )


# (d) an unbound number in one template blocks the whole export (fail-closed).


def test_unbound_number_in_one_template_blocks_all_exports(tmp_path: Path) -> None:
    # funder-a is fully grounded; funder-b asserts a literal 999 that binds to no
    # figure. The whole run must fail closed and write nothing for either format.
    spec = _multi_template_spec(tmp_path, "served 999 clients {clients}")
    out = tmp_path / "out"
    code = main(["run", "--config", str(spec), "--out", str(out), "--reproducible"])
    assert code == 2
    assert not (out / "funder-a").exists()
    assert not (out / "funder-b").exists()


def test_both_templates_grounded_run_succeeds(tmp_path: Path) -> None:
    spec = _multi_template_spec(tmp_path, "we served {clients}")
    out = tmp_path / "out"
    code = main(["run", "--config", str(spec), "--out", str(out), "--reproducible"])
    assert code == 0
    assert (out / "funder-a" / "receipts.json").exists()
    assert (out / "funder-b" / "receipts.json").exists()
