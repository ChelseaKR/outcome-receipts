"""A Word export that says what ``report.md`` says, gated again on its own bytes.

Funder portals take Word files, so staff paste ``report.md`` into Word by hand:
the one step after the grounding gate where a number can change. ``run --format
docx`` writes ``report.docx`` beside ``report.md`` instead, and this module is
both halves of it.

* :func:`render_docx` converts the exported ``report.md`` text -- the artifact the
  gate already passed -- into an Office Open XML document. It is a pure function
  of that text and the locale: no clock, no randomness, every zip entry stored
  uncompressed under one fixed timestamp, so one report is always one byte
  sequence.
* :func:`read_docx` reads a document back out of its bytes and refuses anything
  this module does not itself write: another part, a part named twice, a
  compressed or encrypted entry, an element or attribute outside the closed
  vocabulary below, a document type declaration, an entity, a comment, a
  processing instruction, a CDATA section, or text outside a text run.

The strictness is the point. The gate has to read the document a funder opens,
not the in-memory object that produced it -- a renderer checked against itself
cannot fail -- so the reader has to see every character Word would render, and
the only way to be sure of that is to accept nothing it does not understand. A
document someone opened and saved again is a different document, and is refused
as one.

The XML is read with the standard library's expat parser, driven directly with
the refusals ``defusedxml`` installs: a document type declaration is refused
before anything inside it is processed, so no entity can be declared, expanded,
or fetched, and an undeclared one is a parse error. This package has no runtime
dependencies, which is why that defence is written here rather than imported.

Charts are not embedded. Rasterizing the SVG needs a native dependency this
package does not take, so each chart's image line becomes one sentence naming its
file in the export, followed by the data table ``report.md`` already carries --
the same numbers, each of them a figure display. See
``docs/decisions/0014-the-word-export-is-gated-on-its-own-bytes.md``.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar, Literal, NoReturn
from xml.parsers import expat

from outcome_receipts.copy import Locale, get_copy, normalize_locale

DOCX_NAME = "report.docx"

RunKind = Literal["plain", "bold", "code"]

#: Body text carries no paragraph style; these are the only styles written.
BODY = ""
HEADING_STYLES = ("Heading1", "Heading2", "Heading3")
LIST_STYLES = ("ListBullet", "ListBullet2")
_PARAGRAPH_STYLES = frozenset((*HEADING_STYLES, *LIST_STYLES))

# The largest document, and part, this module reads. Every part is stored rather
# than compressed, so a part's declared size is the number of bytes read and a
# hostile archive is refused by its directory before anything is inflated.
_MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
_MAX_PART_BYTES = 32 * 1024 * 1024

# One timestamp for every entry: 1980-01-01 is the earliest a zip can record.
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)

# US Letter with one-inch margins leaves 6.5 inches of text, in twentieths of a point.
_TEXT_WIDTH = 9360


class DocxError(ValueError):
    """A report that cannot become a document, or a document this module did not write."""


@dataclass(frozen=True)
class Run:
    """A span of text in one format."""

    text: str
    kind: RunKind = "plain"


@dataclass(frozen=True)
class Paragraph:
    """Body text, a heading, or a list item, told apart by ``style``."""

    style: str
    runs: tuple[Run, ...]

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs)


Cell = tuple[Run, ...]


@dataclass(frozen=True)
class Table:
    """A table. ``header`` marks the first row as the header row a reader announces."""

    rows: tuple[tuple[Cell, ...], ...]
    header: bool

    @property
    def text(self) -> str:
        return "\n".join(
            " | ".join("".join(run.text for run in cell) for cell in row) for row in self.rows
        )


Block = Paragraph | Table


def narrative_text(blocks: tuple[Block, ...]) -> str:
    """The narrative region: everything after the title, up to the first section heading.

    It is the region ``verify`` grounds in ``report.md`` -- title lines skipped,
    stopping at the first ``##`` -- read here from paragraph styles rather than
    from Markdown prefixes, so the two gates hold the same prose.
    """

    parts: list[str] = []
    for block in blocks:
        if isinstance(block, Paragraph) and block.style == HEADING_STYLES[1]:
            break
        if isinstance(block, Paragraph) and block.style == HEADING_STYLES[0]:
            continue
        parts.append(block.text)
    return "\n".join(parts).strip()


def document_title(blocks: tuple[Block, ...]) -> str:
    """The report title: the text of a leading first-level heading, or empty."""

    first = blocks[0] if blocks else None
    if isinstance(first, Paragraph) and first.style == HEADING_STYLES[0]:
        return first.text
    return ""


@dataclass(frozen=True)
class DocxText:
    """What a document says, read back out of its bytes."""

    title: str
    language: Locale
    blocks: tuple[Block, ...]

    @property
    def text(self) -> str:
        """Every character the document renders, block by block."""

        return "\n".join(block.text for block in self.blocks)

    @property
    def narrative(self) -> str:
        return narrative_text(self.blocks)


# --- report.md to blocks ---------------------------------------------------------

_HEADING = re.compile(r"(#{1,3}) (.*)")
_BULLET = re.compile(r"( *)- (.*)")
_IMAGE = re.compile(r"!\[(.*)\]\((.*)\)")
_TABLE_LINE = re.compile(r"\|.*\|")
_SEPARATOR = re.compile(r"\|(?:[ :]*-[-: ]*\|)+")
_INLINE = re.compile(r"\*\*(.+?)\*\*|`([^`]+)`")


def _runs(text: str) -> tuple[Run, ...]:
    """One line as runs, reading a matched ``**bold**`` pair and a ``code`` span.

    Only the markers of a matched pair are removed. An unmatched ``**`` or
    backtick stays in the text as it was written.
    """

    runs: list[Run] = []
    position = 0
    for match in _INLINE.finditer(text):
        runs.append(Run(text[position : match.start()]))
        bold, code = match.group(1), match.group(2)
        runs.append(Run(bold, "bold") if bold is not None else Run(code, "code"))
        position = match.end()
    runs.append(Run(text[position:]))
    return tuple(run for run in runs if run.text)


def _emphasized(cell: Cell) -> Cell:
    return tuple(Run(run.text, "bold") if run.kind == "plain" else run for run in cell)


def _table(lines: list[str]) -> Table | None:
    """Pipe-table lines as a table; a separator after the first row makes it the header."""

    header = len(lines) > 1 and _SEPARATOR.fullmatch(lines[1]) is not None
    texts = [
        tuple(cell.strip() for cell in line[1:-1].split("|"))
        for line in lines
        if _SEPARATOR.fullmatch(line) is None
    ]
    if not texts:
        return None
    width = max(len(row) for row in texts)
    rows: list[tuple[Cell, ...]] = []
    for index, row in enumerate(texts):
        cells = tuple(_runs(cell) for cell in (*row, *([""] * (width - len(row)))))
        rows.append(tuple(_emphasized(cell) for cell in cells) if header and index == 0 else cells)
    return Table(tuple(rows), header)


class _BlockBuilder:
    """Accumulate report lines into paragraphs and tables, in order."""

    def __init__(self, chart_note: str) -> None:
        self._chart_note = chart_note
        self._blocks: list[Block] = []
        self._lines: list[str] = []
        self._table: list[str] = []

    def feed(self, line: str) -> None:
        if _TABLE_LINE.fullmatch(line):
            self._end_paragraph()
            self._table.append(line)
            return
        self._end_table()
        if not line.strip():
            self._end_paragraph()
            return
        block = self._structural(line)
        if block is None:
            self._lines.append(line)
            return
        self._end_paragraph()
        self._blocks.append(block)

    def finish(self) -> tuple[Block, ...]:
        self._end_table()
        self._end_paragraph()
        return tuple(self._blocks)

    def _structural(self, line: str) -> Paragraph | None:
        heading = _HEADING.fullmatch(line)
        if heading is not None:
            return Paragraph(HEADING_STYLES[len(heading.group(1)) - 1], _runs(heading.group(2)))
        bullet = _BULLET.fullmatch(line)
        if bullet is not None:
            style = LIST_STYLES[0] if len(bullet.group(1)) < 2 else LIST_STYLES[1]
            return Paragraph(style, _runs(bullet.group(2)))
        image = _IMAGE.fullmatch(line)
        if image is not None:
            note = self._chart_note.format(alt=image.group(1), path=image.group(2))
            return Paragraph(BODY, (Run(note),))
        return None

    def _end_paragraph(self) -> None:
        if self._lines:
            self._blocks.append(Paragraph(BODY, _runs(" ".join(self._lines))))
            self._lines.clear()

    def _end_table(self) -> None:
        if self._table:
            table = _table(self._table)
            if table is not None:
                self._blocks.append(table)
            self._table.clear()


def document_blocks(report_text: str, *, locale: str) -> tuple[Block, ...]:
    """The blocks ``report.md`` becomes in a Word document.

    It reads the Markdown ``render_report`` writes -- a title, ``##`` and ``###``
    headings, paragraphs, pipe tables, ``-`` bullets one level deep, ``**bold**``
    and ``code`` spans, and one image line per chart -- and keeps every other line
    as text, so a line it does not recognise is shown as written rather than
    dropped. Only markup is removed: heading hashes, bullet dashes, table pipes and
    separator rows, and matched emphasis markers. An image line becomes a
    sentence naming the chart's file, because the image is not embedded, and its
    alternative text is kept in that sentence.
    """

    builder = _BlockBuilder(get_copy(locale).docx_chart_note_template)
    for line in report_text.split("\n"):
        builder.feed(line)
    return builder.finish()


# --- blocks to OOXML ---------------------------------------------------------------

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_XML_SPACE = "http://www.w3.org/XML/1998/namespace space"
_CORE_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
_DC_NS = "http://purl.org/dc/elements/1.1/"
_PACKAGE_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
_OFFICE_RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml"
_DECLARATION = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'

_CONTENT_TYPES = (
    _DECLARATION
    + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    + '<Default Extension="rels" '
    + 'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    + '<Default Extension="xml" ContentType="application/xml"/>'
    + f'<Override PartName="/word/document.xml" ContentType="{_TYPE}.document.main+xml"/>'
    + f'<Override PartName="/word/styles.xml" ContentType="{_TYPE}.styles+xml"/>'
    + f'<Override PartName="/word/numbering.xml" ContentType="{_TYPE}.numbering+xml"/>'
    + f'<Override PartName="/word/settings.xml" ContentType="{_TYPE}.settings+xml"/>'
    + '<Override PartName="/docProps/core.xml" '
    + 'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
    + "</Types>"
)

_ROOT_RELS = (
    _DECLARATION
    + f'<Relationships xmlns="{_PACKAGE_RELS}">'
    + f'<Relationship Id="rId1" Type="{_OFFICE_RELS}/officeDocument" Target="word/document.xml"/>'
    + f'<Relationship Id="rId2" Type="{_PACKAGE_RELS}/metadata/core-properties" '
    + 'Target="docProps/core.xml"/>'
    + "</Relationships>"
)

_DOCUMENT_RELS = (
    _DECLARATION
    + f'<Relationships xmlns="{_PACKAGE_RELS}">'
    + f'<Relationship Id="rId1" Type="{_OFFICE_RELS}/styles" Target="styles.xml"/>'
    + f'<Relationship Id="rId2" Type="{_OFFICE_RELS}/numbering" Target="numbering.xml"/>'
    + f'<Relationship Id="rId3" Type="{_OFFICE_RELS}/settings" Target="settings.xml"/>'
    + "</Relationships>"
)

_SETTINGS = (
    _DECLARATION
    + f'<w:settings xmlns:w="{_W_NS}"><w:compat>'
    + '<w:compatSetting w:name="compatibilityMode" '
    + 'w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>'
    + "</w:compat></w:settings>"
)


def _bullet_level(level: int, symbol: str, indent: int) -> str:
    return (
        f'<w:lvl w:ilvl="{level}"><w:start w:val="1"/><w:numFmt w:val="bullet"/>'
        f'<w:lvlText w:val="{symbol}"/><w:lvlJc w:val="left"/>'
        f'<w:pPr><w:ind w:left="{indent}" w:hanging="360"/></w:pPr></w:lvl>'
    )


_NUMBERING = (
    _DECLARATION
    + f'<w:numbering xmlns:w="{_W_NS}">'
    + '<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/>'
    + _bullet_level(0, "•", 720)
    + _bullet_level(1, "◦", 1440)
    + "</w:abstractNum>"
    + '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
    + "</w:numbering>"
)


def _heading_style(level: int, size: int) -> str:
    # The built-in name ("heading 1") is what makes Word, and a screen reader
    # reading through it, treat the style as a heading at that outline level.
    return (
        f'<w:style w:type="paragraph" w:styleId="Heading{level}">'
        f'<w:name w:val="heading {level}"/><w:basedOn w:val="Normal"/>'
        '<w:next w:val="Normal"/><w:uiPriority w:val="9"/><w:qFormat/>'
        '<w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/>'
        f'<w:outlineLvl w:val="{level - 1}"/></w:pPr>'
        f'<w:rPr><w:b/><w:sz w:val="{size}"/><w:szCs w:val="{size}"/></w:rPr>'
        "</w:style>"
    )


def _list_style(style_id: str, name: str, level: int, indent: int) -> str:
    # A list style carries its numbering, so a list item is announced as one
    # without the document body naming a numbering instance itself.
    return (
        f'<w:style w:type="paragraph" w:styleId="{style_id}">'
        f'<w:name w:val="{name}"/><w:basedOn w:val="Normal"/>'
        f'<w:pPr><w:numPr><w:ilvl w:val="{level}"/><w:numId w:val="1"/></w:numPr>'
        f'<w:spacing w:after="60"/><w:ind w:left="{indent}" w:hanging="360"/></w:pPr>'
        "</w:style>"
    )


def _styles(language: str) -> str:
    borders = "".join(
        f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        for side in ("top", "left", "bottom", "right", "insideH", "insideV")
    )
    return (
        _DECLARATION
        + f'<w:styles xmlns:w="{_W_NS}"><w:docDefaults><w:rPrDefault><w:rPr>'
        + '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Calibri" w:cs="Calibri"/>'
        + '<w:sz w:val="22"/><w:szCs w:val="22"/>'
        + f'<w:lang w:val="{language}" w:eastAsia="{language}" w:bidi="{language}"/>'
        + "</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>"
        + '<w:spacing w:after="160" w:line="259" w:lineRule="auto"/>'
        + "</w:pPr></w:pPrDefault></w:docDefaults>"
        + '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        + '<w:name w:val="Normal"/><w:qFormat/></w:style>'
        + _heading_style(1, 36)
        + _heading_style(2, 30)
        + _heading_style(3, 26)
        + _list_style(LIST_STYLES[0], "List Bullet", 0, 720)
        + _list_style(LIST_STYLES[1], "List Bullet 2", 1, 1440)
        + '<w:style w:type="character" w:styleId="Code"><w:name w:val="Code"/>'
        + '<w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/></w:rPr>'
        + "</w:style>"
        + '<w:style w:type="table" w:default="1" w:styleId="TableNormal">'
        + '<w:name w:val="Normal Table"/><w:tblPr><w:tblCellMar>'
        + '<w:left w:w="108" w:type="dxa"/><w:right w:w="108" w:type="dxa"/>'
        + "</w:tblCellMar></w:tblPr></w:style>"
        + '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/>'
        + f'<w:basedOn w:val="TableNormal"/><w:tblPr><w:tblBorders>{borders}</w:tblBorders>'
        + "</w:tblPr></w:style></w:styles>"
    )


def _core(title: str, language: str) -> str:
    return (
        _DECLARATION
        + f'<cp:coreProperties xmlns:cp="{_CORE_NS}" xmlns:dc="{_DC_NS}">'
        + f"<dc:title>{_escape(title)}</dc:title><dc:language>{language}</dc:language>"
        + "</cp:coreProperties>"
    )


_SECTION = (
    '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
    '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
    'w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
)

# Every character XML 1.0 can carry. Anything else is refused, never dropped: a
# document that silently lost a character would no longer say what report.md says.
_NOT_XML = re.compile("[^\t\n\r\u0020-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")


def _escape(text: str) -> str:
    bad = _NOT_XML.search(text)
    if bad is not None:
        raise DocxError(
            f"the report contains U+{ord(bad.group()):04X}, a character a Word document "
            "cannot carry"
        )
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\r", "&#13;")
    )


_RUN_PROPERTIES: dict[RunKind, str] = {
    "plain": "",
    "bold": "<w:rPr><w:b/></w:rPr>",
    "code": '<w:rPr><w:rStyle w:val="Code"/></w:rPr>',
}


def _run_xml(run: Run) -> str:
    pieces: list[str] = []
    for index, segment in enumerate(run.text.split("\t")):
        if index:
            pieces.append("<w:tab/>")
        if segment:
            pieces.append(f'<w:t xml:space="preserve">{_escape(segment)}</w:t>')
    return f"<w:r>{_RUN_PROPERTIES[run.kind]}{''.join(pieces)}</w:r>"


def _paragraph_xml(paragraph: Paragraph) -> str:
    style = f'<w:pPr><w:pStyle w:val="{paragraph.style}"/></w:pPr>' if paragraph.style else ""
    return f"<w:p>{style}{''.join(_run_xml(run) for run in paragraph.runs)}</w:p>"


def _table_xml(table: Table) -> str:
    width = _TEXT_WIDTH // len(table.rows[0])
    grid = f'<w:gridCol w:w="{width}"/>' * len(table.rows[0])
    rows: list[str] = []
    for index, row in enumerate(table.rows):
        header = "<w:trPr><w:tblHeader/></w:trPr>" if table.header and index == 0 else ""
        cells = "".join(
            f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/></w:tcPr>'
            f"<w:p>{''.join(_run_xml(run) for run in cell)}</w:p></w:tc>"
            for cell in row
        )
        rows.append(f"<w:tr>{header}{cells}</w:tr>")
    return (
        '<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="5000" w:type="pct"/>'
        f"</w:tblPr><w:tblGrid>{grid}</w:tblGrid>{''.join(rows)}</w:tbl>"
    )


def _document(blocks: tuple[Block, ...]) -> str:
    body = "".join(
        _paragraph_xml(block) if isinstance(block, Paragraph) else _table_xml(block)
        for block in blocks
    )
    return (
        _DECLARATION
        + f'<w:document xmlns:w="{_W_NS}"><w:body>{body}{_SECTION}</w:body></w:document>'
    )


# The parts, in the order they are written. Only core.xml and document.xml vary
# with the report; every other part is a constant of this module and is compared
# byte for byte on the way back in.
_PART_NAMES = (
    "[Content_Types].xml",
    "_rels/.rels",
    "docProps/core.xml",
    "word/_rels/document.xml.rels",
    "word/document.xml",
    "word/styles.xml",
    "word/numbering.xml",
    "word/settings.xml",
)


def _constant_parts(language: str) -> dict[str, str]:
    return {
        "[Content_Types].xml": _CONTENT_TYPES,
        "_rels/.rels": _ROOT_RELS,
        "word/_rels/document.xml.rels": _DOCUMENT_RELS,
        "word/styles.xml": _styles(language),
        "word/numbering.xml": _NUMBERING,
        "word/settings.xml": _SETTINGS,
    }


def _archive(parts: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for name in _PART_NAMES:
            # Every field that could differ by clock or platform is pinned: the
            # timestamp, the creating system, and the file attributes.
            info = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, parts[name].encode("utf-8"))
    return buffer.getvalue()


def render_docx(report_text: str, *, locale: str) -> bytes:
    """Render the exported ``report.md`` text as a Word document's bytes.

    Raises :class:`DocxError` for a character XML cannot carry rather than
    dropping it.
    """

    language = normalize_locale(locale)
    blocks = document_blocks(report_text, locale=language)
    parts = {
        **_constant_parts(language),
        "docProps/core.xml": _core(document_title(blocks), language),
        "word/document.xml": _document(blocks),
    }
    return _archive(parts)


# --- OOXML back to blocks ----------------------------------------------------------


def _refuse(what: str) -> Callable[..., NoReturn]:
    def refuse(*_args: object) -> NoReturn:
        raise DocxError(f"contains {what}, which this tool never writes")

    return refuse


def _parser() -> expat.XMLParserType:
    """An expat parser holding every refusal a hostile XML part could need.

    These are ``defusedxml``'s refusals. A document type declaration is refused
    the moment it starts, so no entity -- general, parameter, or external -- can
    be declared, and a reference to an undeclared one is an expat error.
    """

    parser = expat.ParserCreate(encoding="UTF-8", namespace_separator=" ")
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.StartDoctypeDeclHandler = _refuse("a document type declaration")
    parser.EntityDeclHandler = _refuse("an entity declaration")
    parser.UnparsedEntityDeclHandler = _refuse("an unparsed entity declaration")
    parser.ExternalEntityRefHandler = _refuse("an external entity reference")
    parser.NotationDeclHandler = _refuse("a notation declaration")
    parser.SkippedEntityHandler = _refuse("an entity reference")
    parser.ProcessingInstructionHandler = _refuse("a processing instruction")
    parser.CommentHandler = _refuse("a comment")
    parser.StartCdataSectionHandler = _refuse("a CDATA section")
    parser.buffer_text = True
    return parser


def _parse(parser: expat.XMLParserType, data: bytes, part: str) -> None:
    try:
        parser.Parse(data, True)
    except expat.ExpatError as exc:
        raise DocxError(f"{part} is not well-formed XML: {exc}") from exc
    except DocxError as exc:
        raise DocxError(f"{part} {exc}") from exc


def _check_entries(infos: list[zipfile.ZipInfo]) -> None:
    names = [info.filename for info in infos]
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise DocxError("it names a part more than once: " + ", ".join(repeated))
    unknown = sorted(set(names) - set(_PART_NAMES))
    if unknown:
        raise DocxError("it carries a part this tool never writes: " + ", ".join(unknown))
    missing = [name for name in _PART_NAMES if name not in names]
    if missing:
        raise DocxError("it lacks a part this tool always writes: " + ", ".join(missing))
    for info in infos:
        if info.compress_type != zipfile.ZIP_STORED:
            raise DocxError(f"{info.filename} is compressed, and this tool stores every part")
        if info.flag_bits & 0x1:
            raise DocxError(f"{info.filename} is encrypted")
        if info.file_size > _MAX_PART_BYTES:
            raise DocxError(f"{info.filename} declares {info.file_size} bytes")


def _parts(data: bytes) -> dict[str, bytes]:
    if len(data) > _MAX_DOCUMENT_BYTES:
        raise DocxError(f"it is {len(data)} bytes, larger than this tool reads")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError, EOFError, ValueError) as exc:
        raise DocxError(f"it is not a zip archive: {exc}") from exc
    with archive:
        infos = archive.infolist()
        _check_entries(infos)
        try:
            return {info.filename: archive.read(info) for info in infos}
        except (zipfile.BadZipFile, OSError, EOFError, ValueError, NotImplementedError) as exc:
            raise DocxError(f"a part cannot be read: {exc}") from exc


_CORE_ROOT = f"{_CORE_NS} coreProperties"
_CORE_FIELDS = {f"{_DC_NS} title": "title", f"{_DC_NS} language": "language"}


class _CoreReader:
    """Read the title and language out of ``docProps/core.xml``, and nothing else."""

    def __init__(self) -> None:
        self._depth = 0
        self._current = ""
        self._values: dict[str, list[str]] = {}

    def read(self, data: bytes) -> tuple[str, Locale]:
        parser = _parser()
        parser.StartElementHandler = self._start
        parser.EndElementHandler = self._end
        parser.CharacterDataHandler = self._chars
        _parse(parser, data, "docProps/core.xml")
        if set(self._values) != set(_CORE_FIELDS.values()):
            raise DocxError("docProps/core.xml does not carry one title and one language")
        language = "".join(self._values["language"])
        if language not in ("en", "es"):
            raise DocxError(
                f"docProps/core.xml names a language this tool never writes: {language!r}"
            )
        return "".join(self._values["title"]), normalize_locale(language)

    def _start(self, name: str, attributes: dict[str, str]) -> None:
        field_name = _CORE_FIELDS.get(name, "") if self._depth == 1 else ""
        known = name == _CORE_ROOT if self._depth == 0 else bool(field_name)
        if not known or attributes or field_name in self._values:
            raise DocxError(f"contains {name!r}, which this tool never writes")
        if field_name:
            self._values[field_name] = []
            self._current = field_name
        self._depth += 1

    def _end(self, _name: str) -> None:
        self._depth -= 1
        self._current = ""

    def _chars(self, data: str) -> None:
        if not self._current:
            raise DocxError("contains text outside a property")
        self._values[self._current].append(data)


# The closed vocabulary of word/document.xml: each element this module writes, and
# the parents it is written under. The empty string is the document root's parent.
_PARENTS: dict[str, frozenset[str]] = {
    "document": frozenset({""}),
    "body": frozenset({"document"}),
    "p": frozenset({"body", "tc"}),
    "pPr": frozenset({"p"}),
    "pStyle": frozenset({"pPr"}),
    "r": frozenset({"p"}),
    "rPr": frozenset({"r"}),
    "b": frozenset({"rPr"}),
    "rStyle": frozenset({"rPr"}),
    "t": frozenset({"r"}),
    "tab": frozenset({"r"}),
    "tbl": frozenset({"body"}),
    "tblPr": frozenset({"tbl"}),
    "tblStyle": frozenset({"tblPr"}),
    "tblW": frozenset({"tblPr"}),
    "tblGrid": frozenset({"tbl"}),
    "gridCol": frozenset({"tblGrid"}),
    "tr": frozenset({"tbl"}),
    "trPr": frozenset({"tr"}),
    "tblHeader": frozenset({"trPr"}),
    "tc": frozenset({"tr"}),
    "tcPr": frozenset({"tc"}),
    "tcW": frozenset({"tcPr"}),
    "sectPr": frozenset({"body"}),
    "pgSz": frozenset({"sectPr"}),
    "pgMar": frozenset({"sectPr"}),
}

_NUMERIC = re.compile(r"[0-9]{1,6}")


def _numeric(value: str) -> bool:
    return _NUMERIC.fullmatch(value) is not None


def _one_of(*values: str) -> Callable[[str], bool]:
    return frozenset(values).__contains__


# The attributes each element may carry, and the values each may take. An element
# absent from this table carries none.
_ATTRIBUTES: dict[str, dict[str, Callable[[str], bool]]] = {
    "pStyle": {"val": _one_of(*_PARAGRAPH_STYLES)},
    "rStyle": {"val": _one_of("Code")},
    "t": {"xml:space": _one_of("preserve")},
    "tblStyle": {"val": _one_of("TableGrid")},
    "tblW": {"w": _numeric, "type": _one_of("pct")},
    "gridCol": {"w": _numeric},
    "tcW": {"w": _numeric, "type": _one_of("dxa")},
    "pgSz": {"w": _numeric, "h": _numeric},
    "pgMar": dict.fromkeys(
        ("top", "right", "bottom", "left", "header", "footer", "gutter"), _numeric
    ),
}


def _local(name: str) -> str:
    namespace, _, local = name.rpartition(" ")
    if namespace != _W_NS:
        raise DocxError(f"contains an element outside WordprocessingML: {name!r}")
    return local


def _check_attributes(element: str, attributes: dict[str, str]) -> None:
    allowed = _ATTRIBUTES.get(element, {})
    for key, value in attributes.items():
        namespace, _, local = key.rpartition(" ")
        name = local if namespace == _W_NS else "xml:space" if key == _XML_SPACE else key
        check = allowed.get(name)
        if check is None or not check(value):
            raise DocxError(
                f"contains an attribute this tool never writes: {name}={value!r} on w:{element}"
            )


@dataclass
class _PendingParagraph:
    style: str = BODY
    runs: list[Run] = field(default_factory=list)


class _DocumentReader:
    """Rebuild the blocks of ``word/document.xml``, refusing anything unfamiliar."""

    def __init__(self) -> None:
        self._stack: list[str] = []
        self._blocks: list[Block] = []
        self._paragraph = _PendingParagraph()
        self._kind: RunKind = "plain"
        self._text: list[str] = []
        self._in_text = False
        self._cell: list[Paragraph] = []
        self._row: list[Cell] = []
        self._rows: list[tuple[Cell, ...]] = []
        self._header_rows: list[int] = []

    def read(self, data: bytes) -> tuple[Block, ...]:
        parser = _parser()
        parser.StartElementHandler = self._start
        parser.EndElementHandler = self._end
        parser.CharacterDataHandler = self._chars
        _parse(parser, data, "word/document.xml")
        return tuple(self._blocks)

    def _start(self, name: str, attributes: dict[str, str]) -> None:
        local = _local(name)
        parent = self._stack[-1] if self._stack else ""
        if parent not in _PARENTS.get(local, frozenset()):
            raise DocxError(
                f"contains an element this tool never writes there: w:{local} "
                f"in {'w:' + parent if parent else 'the document root'}"
            )
        _check_attributes(local, attributes)
        self._stack.append(local)
        opener = self._OPENERS.get(local)
        if opener is not None:
            opener(self, attributes)

    def _end(self, _name: str) -> None:
        closer = self._CLOSERS.get(self._stack.pop())
        if closer is not None:
            closer(self)

    def _chars(self, data: str) -> None:
        if not self._in_text:
            raise DocxError("contains text outside a text run")
        self._text.append(data)

    def _open_paragraph(self, _attributes: dict[str, str]) -> None:
        self._paragraph = _PendingParagraph()

    def _open_style(self, attributes: dict[str, str]) -> None:
        style = attributes.get(f"{_W_NS} val")
        if style is None:
            raise DocxError("contains a paragraph style with no name")
        self._paragraph.style = style

    def _open_run(self, _attributes: dict[str, str]) -> None:
        self._kind = "plain"
        self._text = []

    def _open_bold(self, _attributes: dict[str, str]) -> None:
        self._set_kind("bold")

    def _open_code(self, _attributes: dict[str, str]) -> None:
        self._set_kind("code")

    def _set_kind(self, kind: RunKind) -> None:
        if self._kind != "plain":
            raise DocxError("contains a run in two formats, which this tool never writes")
        self._kind = kind

    def _open_text(self, _attributes: dict[str, str]) -> None:
        self._in_text = True

    def _open_tab(self, _attributes: dict[str, str]) -> None:
        self._text.append("\t")

    def _open_table(self, _attributes: dict[str, str]) -> None:
        self._rows = []
        self._header_rows = []

    def _open_row(self, _attributes: dict[str, str]) -> None:
        self._row = []

    def _open_header(self, _attributes: dict[str, str]) -> None:
        self._header_rows.append(len(self._rows))

    def _open_cell(self, _attributes: dict[str, str]) -> None:
        self._cell = []

    def _close_text(self) -> None:
        self._in_text = False

    def _close_run(self) -> None:
        text = "".join(self._text)
        if not text:
            raise DocxError("contains a run with no text, which this tool never writes")
        self._paragraph.runs.append(Run(text, self._kind))

    def _close_paragraph(self) -> None:
        paragraph = Paragraph(self._paragraph.style, tuple(self._paragraph.runs))
        if self._stack[-1] == "tc":
            self._cell.append(paragraph)
        else:
            self._blocks.append(paragraph)

    def _close_cell(self) -> None:
        if len(self._cell) != 1 or self._cell[0].style:
            raise DocxError("contains a table cell other than one unstyled paragraph")
        self._row.append(self._cell[0].runs)

    def _close_row(self) -> None:
        self._rows.append(tuple(self._row))

    def _close_table(self) -> None:
        widths = {len(row) for row in self._rows}
        if len(widths) != 1 or 0 in widths:
            raise DocxError("contains a table whose rows are not all one width")
        if self._header_rows not in ([], [0]):
            raise DocxError("marks a row other than the first as the table's header")
        self._blocks.append(Table(tuple(self._rows), header=self._header_rows == [0]))

    _OPENERS: ClassVar[dict[str, Callable[[_DocumentReader, dict[str, str]], None]]] = {
        "p": _open_paragraph,
        "pStyle": _open_style,
        "r": _open_run,
        "b": _open_bold,
        "rStyle": _open_code,
        "t": _open_text,
        "tab": _open_tab,
        "tbl": _open_table,
        "tr": _open_row,
        "tblHeader": _open_header,
        "tc": _open_cell,
    }
    _CLOSERS: ClassVar[dict[str, Callable[[_DocumentReader], None]]] = {
        "t": _close_text,
        "r": _close_run,
        "p": _close_paragraph,
        "tc": _close_cell,
        "tr": _close_row,
        "tbl": _close_table,
    }


def read_docx(data: bytes) -> DocxText:
    """Read what a document this module wrote says, or refuse it naming why.

    Every part must be one this module writes, stored, named once, and every
    constant part must be byte-identical to the one this module writes for the
    document's declared language. ``word/document.xml`` is then rebuilt into
    blocks through the closed vocabulary above, so the text returned is every
    character the document can render and nothing is skipped as unfamiliar.
    """

    parts = _parts(data)
    title, language = _CoreReader().read(parts["docProps/core.xml"])
    for name, content in _constant_parts(language).items():
        if parts[name] != content.encode("utf-8"):
            raise DocxError(f"{name} is not the part this tool writes")
    blocks = _DocumentReader().read(parts["word/document.xml"])
    return DocxText(title=title, language=language, blocks=blocks)
