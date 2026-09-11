"""Merge-relevant: the Word export is gated on its own bytes, and verify holds it there.

``run --format docx`` writes ``report.docx`` beside ``report.md``. These tests pin
issue 159's four acceptance criteria against the shipped examples -- the demo's
document grounds and is attested in ``bundle.json``; a number put into it after
export fails verification even when whoever did it also rewrites the digest; a
suppressed cell shows the redaction marker in a document table; two reproducible
runs are byte-identical -- and the refusals that make the reader worth trusting,
each asserted by the words it refuses with, so a refusal that fired for a
different reason cannot pass for this one.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import warnings
import zipfile
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from outcome_receipts.bundle import bundle_manifest
from outcome_receipts.cli import EXIT_GATE_FAIL, EXIT_OK, EXIT_VERIFY_FAIL, main
from outcome_receipts.copy import SUPPORTED_LOCALES, get_copy
from outcome_receipts.docx import (
    DOCX_NAME,
    DocxError,
    Table,
    document_blocks,
    narrative_text,
    read_docx,
    render_docx,
)
from outcome_receipts.grounding import find_numbers
from outcome_receipts.models import REDACTED_DISPLAY

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
HOUSING = EXAMPLES / "housing-demo" / "report.toml"
GRANT = EXAMPLES / "grant-report" / "report.toml"
MULTI = EXAMPLES / "multi-funder" / "report.toml"

# The demo narrative's one sentence carrying a figure, as the document stores it.
NARRATIVE_ANCHOR = b"served 12 clients."


def _run(config: Path, out: Path, *extra: str) -> int:
    ledger = out.parent / f"{out.name}-ledger.jsonl"
    return main(
        [
            *("run", "--config", str(config), "--out", str(out), "--ledger", str(ledger)),
            *("--reproducible", "--approved-by", "CI"),
            *extra,
        ]
    )


def _export(tmp_path: Path, config: Path = HOUSING, name: str = "out") -> Path:
    out = tmp_path / name
    assert _run(config, out, "--format", "docx") == EXIT_OK
    return out


def _verify(
    config: Path, bundle: Path, capsys: pytest.CaptureFixture[str]
) -> tuple[int, dict[str, Any]]:
    capsys.readouterr()
    code = main(["verify", "--config", str(config), "--bundle", str(bundle), "--json"])
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    return code, payload


def _document(payload: dict[str, Any]) -> dict[str, Any]:
    document: dict[str, Any] = payload["document"]
    return document


def _unbound(document: dict[str, Any]) -> list[str]:
    return [str(span["text"]) for span in document["grounding"]["unbound"]]


def _parts(data: bytes) -> list[tuple[zipfile.ZipInfo, bytes]]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return [(info, archive.read(info)) for info in archive.infolist()]


def _repack(
    data: bytes,
    edit: Callable[[str, bytes], bytes] = lambda _name, content: content,
    *,
    extra: tuple[tuple[str, bytes], ...] = (),
    omit: tuple[str, ...] = (),
    compression: int = zipfile.ZIP_STORED,
) -> bytes:
    """The same document with a part edited, added or left out, or its entries recompressed."""

    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # zipfile warns about a duplicate name, on purpose here
        with zipfile.ZipFile(buffer, "w") as archive:
            for info, content in _parts(data):
                if info.filename in omit:
                    continue
                info.compress_type = compression
                archive.writestr(info, edit(info.filename, content))
            for name, content in extra:
                archive.writestr(zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), content)
    return buffer.getvalue()


def _edit_document(
    data: bytes,
    old: bytes,
    new: bytes,
    *,
    first_of_many: bool = False,
    part: str = "word/document.xml",
) -> bytes:
    """Replace a fragment of one part, ``word/document.xml`` by default, asserting it lands.

    Exactly one occurrence is required unless ``first_of_many``, which replaces
    only the first of several -- and still requires there to be one.
    """

    def edit(name: str, content: bytes) -> bytes:
        if name != part:
            return content
        found = content.count(old)
        assert found >= 1 if first_of_many else found == 1, (old, found)
        return content.replace(old, new, 1)

    return _repack(data, edit)


def _reattest(out: Path) -> None:
    """Rewrite receipts.json's digests to match the files, as whoever edited them could."""

    manifest_path = out / "receipts.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name in manifest["artifacts"]:
        manifest["artifacts"][name] = hashlib.sha256((out / name).read_bytes()).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _reseal(out: Path) -> None:
    """Rewrite bundle.json over the files as they now are, which needs no key."""

    members = {
        path.relative_to(out).as_posix(): path.read_bytes()
        for path in sorted(out.rglob("*"))
        if path.is_file() and path.name != "bundle.json"
    }
    (out / "bundle.json").write_text(bundle_manifest(members), encoding="utf-8")


# --- the four acceptance criteria -------------------------------------------------------


def test_the_demo_document_grounds_and_its_digest_is_in_bundle_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _export(tmp_path)
    data = (out / DOCX_NAME).read_bytes()

    code, payload = _verify(HOUSING, out, capsys)
    document = _document(payload)
    assert code == EXIT_OK
    assert document["checked"] is True
    assert document["ok"] is True
    grounding = document["grounding"]
    assert isinstance(grounding, dict)
    # Not vacuous: the demo narrative states a figure, and the gate bound it.
    assert grounding["total"] == grounding["bound"] >= 1
    assert "12" in read_docx(data).narrative

    bundle = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
    digest = hashlib.blake2b(data, digest_size=32).hexdigest()
    assert {"name": DOCX_NAME, "digest": digest} in bundle["members"]
    manifest = json.loads((out / "receipts.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"][DOCX_NAME] == hashlib.sha256(data).hexdigest()
    assert main(["verify-bundle", "--dir", str(out)]) == EXIT_OK


def test_a_number_put_into_the_narrative_fails_verify_even_with_every_digest_rewritten(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The document's own grounding catches it, and nothing else in the check does.

    The same number goes into ``report.md`` and the document, and both digests
    are rewritten, so the document still says exactly what the report says and
    every artifact digest matches. What is left to fail is the gate over the
    document's narrative -- which is the check this test exists for.
    """

    out = _export(tmp_path)
    report = out / "report.md"
    text = report.read_text(encoding="utf-8")
    assert text.count("served 12 clients.") == 1
    report.write_text(
        text.replace("served 12 clients.", "served 12 clients and 4242 families."),
        encoding="utf-8",
    )
    tampered = _edit_document(
        (out / DOCX_NAME).read_bytes(),
        NARRATIVE_ANCHOR,
        b"served 12 clients and 4242 families.",
    )
    (out / DOCX_NAME).write_bytes(tampered)
    _reattest(out)

    code, payload = _verify(HOUSING, out, capsys)
    document = _document(payload)
    assert code == EXIT_VERIFY_FAIL
    assert all(artifact["ok"] for artifact in payload["artifacts"])
    assert document["ok"] is False
    assert "4242" in _unbound(document)
    assert "bind to no receipt" in str(document["detail"])
    assert "does not say what report.md says" not in str(document["detail"])


def test_a_number_put_outside_the_narrative_fails_verify_even_with_the_bundle_resealed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Only the comparison with ``report.md`` can see a number outside the narrative.

    The receipts appendix is not gated -- its row counts and hashes are metadata --
    so an edit there binds nothing and grounds nothing. The document now disagrees
    with ``report.md``, whose digest still holds, and that is the failure.
    """

    out = _export(tmp_path)
    tampered = _edit_document(
        (out / DOCX_NAME).read_bytes(),
        b"rows in slice: 12<",
        b"rows in slice: 4242<",
    )
    (out / DOCX_NAME).write_bytes(tampered)
    assert main(["verify-bundle", "--dir", str(out)]) == EXIT_VERIFY_FAIL

    _reattest(out)
    _reseal(out)
    assert main(["verify-bundle", "--dir", str(out)]) == EXIT_OK  # the seal alone is fooled

    code, payload = _verify(HOUSING, out, capsys)
    document = _document(payload)
    assert code == EXIT_VERIFY_FAIL
    assert document["ok"] is False
    assert _unbound(document) == []
    detail = str(document["detail"])
    assert "does not say what report.md says" in detail
    assert "4242" in detail
    assert "does not carry the same digits" in detail


def test_a_suppressed_cell_shows_the_marker_in_a_document_table(tmp_path: Path) -> None:
    out = _export(tmp_path, GRANT)
    read = read_docx((out / DOCX_NAME).read_bytes())
    tables = [block for block in read.blocks if isinstance(block, Table)]
    by_label = {
        "".join(run.text for run in row[0]): "".join(run.text for run in row[1])
        for table in tables
        for row in table.rows
        if len(row) == 2
    }
    assert by_label["Temporary"] == REDACTED_DISPLAY
    assert by_label["Permanent"] == "13"
    marked = (out / "report.md").read_text(encoding="utf-8").count(REDACTED_DISPLAY)
    assert read.text.count(REDACTED_DISPLAY) == marked > 0
    assert all(table.header for table in tables)


def test_two_reproducible_runs_write_byte_identical_documents(tmp_path: Path) -> None:
    first = _export(tmp_path, GRANT, "first")
    second = _export(tmp_path, GRANT, "second")
    data = (first / DOCX_NAME).read_bytes()
    assert data == (second / DOCX_NAME).read_bytes()
    # And not by luck of running inside one clock second: nothing in it reads a clock.
    for info, _content in _parts(data):
        assert info.date_time == (1980, 1, 1, 0, 0, 0)
        assert info.compress_type == zipfile.ZIP_STORED


# --- what the flag does and does not change ----------------------------------------------


def test_without_the_flag_there_is_no_document_and_the_report_is_the_same_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plain = tmp_path / "plain"
    assert _run(GRANT, plain) == EXIT_OK
    with_docx = _export(tmp_path, GRANT, "docx")

    assert not (plain / DOCX_NAME).exists()
    manifest = json.loads((plain / "receipts.json").read_text(encoding="utf-8"))
    assert DOCX_NAME not in manifest["artifacts"]
    for name in ("report.md", "trace.html", "charts/exits-by-destination.svg"):
        assert (plain / name).read_bytes() == (with_docx / name).read_bytes(), name

    code, payload = _verify(GRANT, plain, capsys)
    document = _document(payload)
    assert code == EXIT_OK
    assert document == {
        "checked": False,
        "ok": True,
        "detail": "no document export to check",
        "grounding": None,
    }


def test_every_template_gets_its_own_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _export(tmp_path, MULTI)
    narratives = set()
    for template in ("funder-a", "funder-b"):
        code, payload = _verify(MULTI, out / template, capsys)
        assert code == EXIT_OK, payload
        assert _document(payload)["ok"] is True
        narratives.add(read_docx((out / template / DOCX_NAME).read_bytes()).narrative)
    assert len(narratives) == 2


def test_a_document_the_manifest_does_not_attest_fails_verify(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    assert _run(HOUSING, out) == EXIT_OK
    text = (out / "report.md").read_text(encoding="utf-8")
    (out / DOCX_NAME).write_bytes(render_docx(text, locale="en"))

    code, payload = _verify(HOUSING, out, capsys)
    document = _document(payload)
    assert code == EXIT_VERIFY_FAIL
    assert document["checked"] is True
    assert "does not attest" in str(document["detail"])


def test_an_attested_document_that_is_missing_fails_verify(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _export(tmp_path)
    (out / DOCX_NAME).unlink()
    code, payload = _verify(HOUSING, out, capsys)
    assert code == EXIT_VERIFY_FAIL
    assert "missing" in str(_document(payload)["detail"])


def test_verify_says_whether_it_checked_a_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _export(tmp_path)
    capsys.readouterr()
    assert main(["verify", "--config", str(HOUSING), "--bundle", str(out)]) == EXIT_OK
    assert "document export: checked — report.docx says what report.md says" in (
        capsys.readouterr().out
    )


# --- the export refuses, and writes nothing ------------------------------------------------


def test_the_export_refuses_a_document_that_does_not_say_what_the_report_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real = render_docx

    def drifting(report_text: str, *, locale: str) -> bytes:
        return real(report_text.replace("served 12 clients", "served 13 clients"), locale=locale)

    monkeypatch.setattr("outcome_receipts.cli.render_docx", drifting)
    out = tmp_path / "out"
    capsys.readouterr()
    assert _run(HOUSING, out, "--format", "docx", "--json") == EXIT_GATE_FAIL
    payload = json.loads(capsys.readouterr().out)
    document = payload["document"]
    assert payload["gate_pass"] is False
    assert document["ok"] is False
    assert document["template"] == "report"
    assert "13" in [span["text"] for span in document["grounding"]["unbound"]]
    assert not out.exists() or not any(out.iterdir())
    assert not (tmp_path / "out-ledger.jsonl").exists()


def test_a_character_a_document_cannot_carry_refuses_the_export_and_only_the_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    source = HOUSING.parent
    (spec_dir / "services.csv").write_bytes((source / "services.csv").read_bytes())
    spec = (source / "report.toml").read_text(encoding="utf-8")
    assert spec.count('title = "Housing Program Outcome Report"') == 1
    spec = spec.replace(
        'title = "Housing Program Outcome Report"',
        'title = "Housing Program\\u000BOutcome Report"',
    )
    (spec_dir / "report.toml").write_text(spec, encoding="utf-8")

    assert _run(spec_dir / "report.toml", tmp_path / "markdown") == EXIT_OK
    capsys.readouterr()
    out = tmp_path / "out"
    assert _run(spec_dir / "report.toml", out, "--format", "docx") == EXIT_GATE_FAIL
    err = capsys.readouterr().err
    assert "document gate: FAIL" in err
    assert "U+000B" in err
    assert not out.exists() or not any(out.iterdir())


# --- the reader refuses what this tool never writes ------------------------------------------


@pytest.fixture(scope="module")
def demo_document(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    out = tmp_path_factory.mktemp("demo") / "out"
    assert _run(HOUSING, out, "--format", "docx") == EXIT_OK
    return (out / DOCX_NAME).read_bytes()


def _with_doctype(data: bytes) -> bytes:
    def edit(name: str, content: bytes) -> bytes:
        if name != "word/document.xml":
            return content
        head, _, rest = content.partition(b"?>")
        declared = head + b'?><!DOCTYPE w:document [<!ENTITY n "4242">]>' + rest
        assert declared.count(NARRATIVE_ANCHOR) == 1
        return declared.replace(NARRATIVE_ANCHOR, b"served &n; clients.")

    return _repack(data, edit)


def _styles_changed(data: bytes) -> bytes:
    def edit(name: str, content: bytes) -> bytes:
        if name != "word/styles.xml":
            return content
        assert content.count(b'<w:sz w:val="22"/>') == 1
        return content.replace(b'<w:sz w:val="22"/>', b'<w:sz w:val="2"/>')

    return _repack(data, edit)


REFUSALS: dict[str, tuple[Callable[[bytes], bytes], str]] = {
    "a part it never writes": (
        lambda data: _repack(data, extra=(("word/footer1.xml", b"<w:ftr/>"),)),
        "carries a part this tool never writes: word/footer1.xml",
    ),
    "a part missing": (
        lambda data: _repack(data, omit=("word/numbering.xml",)),
        "lacks a part this tool always writes: word/numbering.xml",
    ),
    "a part named twice": (
        lambda data: _repack(data, extra=(("word/document.xml", b"<x/>"),)),
        "names a part more than once: word/document.xml",
    ),
    "a compressed part": (
        lambda data: _repack(data, compression=zipfile.ZIP_DEFLATED),
        "is compressed",
    ),
    "a changed constant part": (
        _styles_changed,
        "word/styles.xml is not the part this tool writes",
    ),
    "a document type declaration": (_with_doctype, "contains a document type declaration"),
    "a comment": (
        lambda data: _edit_document(data, NARRATIVE_ANCHOR, b"served 12<!-- 4242 --> clients."),
        "contains a comment",
    ),
    "an element it never writes": (
        lambda data: _edit_document(
            data,
            b"<w:rPr><w:b/></w:rPr>",
            b"<w:rPr><w:b/><w:vanish/></w:rPr>",
            first_of_many=True,
        ),
        "never writes there: w:vanish",
    ),
    "an attribute value it never writes": (
        lambda data: _edit_document(
            data, b'<w:pStyle w:val="Heading1"/>', b'<w:pStyle w:val="Title"/>'
        ),
        "val='Title' on w:pStyle",
    ),
    "text outside a run": (
        lambda data: _edit_document(
            data,
            b'<w:r><w:t xml:space="preserve">In the reporting period',
            b'4242<w:r><w:t xml:space="preserve">In the reporting period',
        ),
        "contains text outside a text run",
    ),
    "something that is not a zip": (lambda _data: b"not a document", "is not a zip archive"),
}


@pytest.mark.parametrize("case", sorted(REFUSALS))
def test_the_reader_refuses_what_this_tool_never_writes(demo_document: bytes, case: str) -> None:
    tamper, words = REFUSALS[case]
    tampered = tamper(demo_document)
    assert tampered != demo_document
    with pytest.raises(DocxError, match=re.escape(words)):
        read_docx(tampered)


def test_a_document_the_reader_refuses_fails_verify_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Through ``verify --bundle``, not only through the reader: unreadable is a named failure."""

    out = _export(tmp_path)
    data = (out / DOCX_NAME).read_bytes()
    (out / DOCX_NAME).write_bytes(_repack(data, extra=(("word/footer1.xml", b"<w:ftr/>"),)))
    _reattest(out)
    code, payload = _verify(HOUSING, out, capsys)
    document = _document(payload)
    assert code == EXIT_VERIFY_FAIL
    assert document["grounding"] is None
    assert "is not a document this tool wrote" in document["detail"]
    assert "word/footer1.xml" in document["detail"]


def test_the_narrative_runs_to_the_end_of_a_document_with_no_section_heading() -> None:
    """Every report has sections, but a region reader must not need one to stop."""

    blocks = document_blocks("# Title\n\nServed 12.\n\n- a list item 3", locale="en")
    assert narrative_text(blocks) == "Served 12.\na list item 3"


def test_the_reader_decodes_a_number_written_as_character_references(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A text scan would see ``&#52;&#50;`` and no digit; Word shows ``42``, and so must the gate."""

    out = _export(tmp_path)
    tampered = _edit_document(
        (out / DOCX_NAME).read_bytes(),
        NARRATIVE_ANCHOR,
        b"served 12 clients and &#52;&#50;&#52;&#50; families.",
    )
    (out / DOCX_NAME).write_bytes(tampered)
    _reattest(out)
    assert "4242" in read_docx(tampered).narrative
    code, payload = _verify(HOUSING, out, capsys)
    assert code == EXIT_VERIFY_FAIL
    assert "4242" in _unbound(_document(payload))


# --- the document's own copy ----------------------------------------------------------------


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
def test_the_chart_note_adds_no_number_of_its_own(locale: str) -> None:
    """The note stands in for an image line; a number in it would bind to nothing."""

    note = get_copy(locale).docx_chart_note_template.format(alt="", path="")
    assert find_numbers(note) == []
    assert not any(character.isdecimal() for character in note)


def test_a_spanish_export_is_a_spanish_document(tmp_path: Path) -> None:
    out = tmp_path / "es"
    assert _run(GRANT, out, "--format", "docx", "--locale", "es") == EXIT_OK
    read = read_docx((out / DOCX_NAME).read_bytes())
    assert read.language == "es"
    assert "Gráfico no incrustado en este documento" in read.text


def test_the_document_gates_the_number_a_reader_sees_where_markup_changed_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``**12**%`` is ``12`` to a scan of raw Markdown and ``12%`` to anyone reading it.

    The document is what the funder reads, so its reading is the one gated, and a
    count published as a percent binds to no receipt. Issue 191 records that the
    Markdown gate reads the raw ``12`` instead.
    """

    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "services.csv").write_bytes((HOUSING.parent / "services.csv").read_bytes())
    spec = HOUSING.read_text(encoding="utf-8")
    old = "served {clients_served} clients"
    assert spec.count(old) == 1
    marked_up = spec.replace(old, "served **{clients_served}**% of its clients")
    (spec_dir / "report.toml").write_text(marked_up, encoding="utf-8")

    capsys.readouterr()
    out = tmp_path / "out"
    assert _run(spec_dir / "report.toml", out, "--format", "docx", "--json") == EXIT_GATE_FAIL
    document = json.loads(capsys.readouterr().out)["document"]
    assert [span["text"] for span in document["grounding"]["unbound"]] == ["12%"]


# --- the checks that do not trust the renderer -----------------------------------------------


def _lossy(monkeypatch: pytest.MonkeyPatch, old: str, new: str) -> None:
    """Make the renderer lose something, on the writing side and the checking side alike.

    Both sides then agree -- the document says exactly what the renderer expects it
    to -- so the block comparison passes, and only a check that reads ``report.md``'s
    raw text can see what went missing.
    """

    real = document_blocks

    def lossy(report_text: str, *, locale: str) -> tuple[object, ...]:
        assert old in report_text
        return real(report_text.replace(old, new, 1), locale=locale)

    monkeypatch.setattr("outcome_receipts.docx.document_blocks", lossy)
    monkeypatch.setattr("outcome_receipts.verify.document_blocks", lossy)


def _refused_detail(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> str:
    capsys.readouterr()
    assert _run(HOUSING, tmp_path / "out", "--format", "docx", "--json") == EXIT_GATE_FAIL
    return str(json.loads(capsys.readouterr().out)["document"]["detail"])


def test_a_renderer_that_loses_a_number_is_caught_by_the_raw_digit_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _lossy(monkeypatch, "served 12 clients", "served clients")
    detail = _refused_detail(tmp_path, capsys)
    assert "does not carry the same digits as report.md" in detail
    assert "does not say what report.md says" not in detail


def test_a_renderer_that_loses_a_redaction_marker_is_caught_by_the_raw_marker_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _lossy(monkeypatch, REDACTED_DISPLAY, "")
    detail = _refused_detail(tmp_path, capsys)
    assert f"shows {REDACTED_DISPLAY} 11 time(s) where report.md shows it 12" in detail
    assert "does not say what report.md says" not in detail


DRIFTS: dict[str, tuple[Callable[[bytes], bytes], str]] = {
    "retitled": (
        lambda data: _edit_document(
            data,
            b"<dc:title>Housing Program Outcome Report</dc:title>",
            b"<dc:title>Housing Program Outcome Report 2019</dc:title>",
            part="docProps/core.xml",
        ),
        "its title 'Housing Program Outcome Report 2019' is not report.md's",
    ),
    "a run's format changed": (
        lambda data: _edit_document(data, b"<w:rPr><w:b/></w:rPr>", b"", first_of_many=True),
        "has report.md's text in a different form",
    ),
    "a paragraph added": (
        lambda data: _edit_document(
            data,
            b"<w:sectPr>",
            b'<w:p><w:r><w:t xml:space="preserve">Added later.</w:t></w:r></w:p><w:sectPr>',
        ),
        "it has 40 block(s) where report.md renders 39",
    ),
}


@pytest.mark.parametrize("case", sorted(DRIFTS))
def test_a_document_that_drifted_from_its_report_fails_verify(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    tamper, words = DRIFTS[case]
    out = _export(tmp_path)
    (out / DOCX_NAME).write_bytes(tamper((out / DOCX_NAME).read_bytes()))
    _reattest(out)
    code, payload = _verify(HOUSING, out, capsys)
    assert code == EXIT_VERIFY_FAIL
    assert words in str(_document(payload)["detail"])


# --- more of what the reader refuses ---------------------------------------------------------


@pytest.fixture(scope="module")
def grant_document(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    out = tmp_path_factory.mktemp("grant") / "out"
    assert _run(GRANT, out, "--format", "docx") == EXIT_OK
    return (out / DOCX_NAME).read_bytes()


def _flagged_encrypted(data: bytes) -> bytes:
    """The central directory marks ``word/settings.xml`` encrypted; no other byte changes.

    Written by hand because ``zipfile`` resets an entry's flags when it writes one,
    so a flag set on the ``ZipInfo`` never reaches the archive.
    """

    patched = bytearray(data)
    start = 0
    while True:
        at = patched.find(b"PK\x01\x02", start)
        assert at != -1, "no central directory entry names word/settings.xml"
        length = int.from_bytes(patched[at + 28 : at + 30], "little")
        if patched[at + 46 : at + 46 + length] == b"word/settings.xml":
            flags = int.from_bytes(patched[at + 8 : at + 10], "little") | 0x1
            patched[at + 8 : at + 10] = flags.to_bytes(2, "little")
            return bytes(patched)
        start = at + 4


def _corrupted(data: bytes) -> bytes:
    """One byte of a stored part changed in place, so its CRC no longer matches."""

    assert data.count(NARRATIVE_ANCHOR) == 1
    return data.replace(NARRATIVE_ANCHOR, b"served 17 clients.")


CORE = "docProps/core.xml"
MORE_REFUSALS: dict[str, tuple[Callable[[bytes], bytes], str]] = {
    "a core property it never writes": (
        lambda data: _edit_document(
            data,
            b"</cp:coreProperties>",
            b"<dc:creator>x</dc:creator></cp:coreProperties>",
            part=CORE,
        ),
        "docProps/core.xml contains",
    ),
    "a language it never writes": (
        lambda data: _edit_document(
            data, b"<dc:language>en</dc:language>", b"<dc:language>fr</dc:language>", part=CORE
        ),
        "names a language this tool never writes: 'fr'",
    ),
    "a core property missing": (
        lambda data: _edit_document(data, b"<dc:language>en</dc:language>", b"", part=CORE),
        "does not carry one title and one language",
    ),
    "text between core properties": (
        lambda data: _edit_document(data, b"<dc:title>", b"2019<dc:title>", part=CORE),
        "docProps/core.xml contains text outside a property",
    ),
    "a paragraph style with no name": (
        lambda data: _edit_document(data, b'<w:pStyle w:val="Heading1"/>', b"<w:pStyle/>"),
        "a paragraph style with no name",
    ),
    "a run in two formats": (
        lambda data: _edit_document(
            data, b"<w:rPr><w:b/></w:rPr>", b"<w:rPr><w:b/><w:b/></w:rPr>", first_of_many=True
        ),
        "a run in two formats",
    ),
    "a run with no text": (
        lambda data: _edit_document(data, b"<w:sectPr>", b"<w:p><w:r></w:r></w:p><w:sectPr>"),
        "a run with no text",
    ),
    "an element outside the namespace": (
        lambda data: _edit_document(
            data, b"<w:sectPr>", b'<x:p xmlns:x="urn:elsewhere"/><w:sectPr>'
        ),
        "an element outside WordprocessingML",
    ),
    "a document that is not well-formed": (
        lambda data: _edit_document(data, b"</w:body>", b"</w:bdy>"),
        "is not well-formed XML",
    ),
    "an entry flagged as encrypted": (_flagged_encrypted, "word/settings.xml is encrypted"),
    "a part whose bytes no longer match its CRC": (_corrupted, "a part cannot be read"),
}


@pytest.mark.parametrize("case", sorted(MORE_REFUSALS))
def test_the_reader_refuses_more_than_one_way(demo_document: bytes, case: str) -> None:
    tamper, words = MORE_REFUSALS[case]
    tampered = tamper(demo_document)
    assert tampered != demo_document
    with pytest.raises(DocxError, match=re.escape(words)):
        read_docx(tampered)


TABLE_REFUSALS: dict[str, tuple[bytes, bytes, str]] = {
    "a cell of two paragraphs": (
        b"</w:p></w:tc>",
        b"</w:p><w:p></w:p></w:tc>",
        "a table cell other than one unstyled paragraph",
    ),
    "a row wider than the rest": (
        b"</w:tr>",
        b"<w:tc><w:p></w:p></w:tc></w:tr>",
        "a table whose rows are not all one width",
    ),
    "a header below the first row": (
        b"</w:tr><w:tr>",
        b"</w:tr><w:tr><w:trPr><w:tblHeader/></w:trPr>",
        "marks a row other than the first as the table's header",
    ),
}


@pytest.mark.parametrize("case", sorted(TABLE_REFUSALS))
def test_the_reader_refuses_a_table_this_tool_never_writes(
    grant_document: bytes, case: str
) -> None:
    old, new, words = TABLE_REFUSALS[case]
    tampered = _edit_document(grant_document, old, new, first_of_many=True)
    with pytest.raises(DocxError, match=re.escape(words)):
        read_docx(tampered)


def test_the_reader_refuses_by_declared_size_before_reading(
    demo_document: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("outcome_receipts.docx._MAX_DOCUMENT_BYTES", len(demo_document) - 1)
    with pytest.raises(DocxError, match="larger than this tool reads"):
        read_docx(demo_document)
    monkeypatch.undo()
    monkeypatch.setattr("outcome_receipts.docx._MAX_PART_BYTES", 10)
    with pytest.raises(DocxError, match=r"declares [0-9]+ bytes"):
        read_docx(demo_document)


# --- the renderer never drops what it does not recognise -------------------------------------

_LINES = st.one_of(
    st.sampled_from(
        [
            "# Title 2025",
            "## Heading 3",
            "### Chart 4",
            "- **metric_1** = 12",
            "  - rows in slice: 34",
            "| Category | Value |",
            "|----------|-------|",
            "| Q1 2025 | [SUPPRESSED] |",
            "![Chart 5 (see data table below)](charts/c6.svg)",
            "",
            "12**34**%",
            "`SELECT 1` and **7**",
            "a\tb 8",
            "unmatched ** and ` 9",
        ]
    ),
    st.text(
        alphabet=st.sampled_from(list("ab #|*`-!()[]:,.%$\t\r0123456789é")),
        max_size=40,
    ),
)


@settings(max_examples=150, deadline=None)
@given(st.lists(_LINES, max_size=25))
def test_any_report_text_round_trips_and_keeps_every_letter_and_digit(lines: list[str]) -> None:
    text = "\n".join(lines)
    read = read_docx(render_docx(text, locale="en"))
    assert read.blocks == document_blocks(text, locale="en")
    digits = Counter(c for c in text if c.isdecimal())
    assert Counter(c for c in read.text if c.isdecimal()) == digits
    letters = Counter(c for c in text if c.isalnum())
    assert letters <= Counter(c for c in read.text if c.isalnum())
