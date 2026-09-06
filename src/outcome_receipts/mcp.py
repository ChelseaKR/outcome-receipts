"""A read-only Model Context Protocol server over standard input and output.

The load-bearing invariant of this project is that numbers never come from a
model. The Bedrock drafter is one integration, but organizations draft in
whatever assistant they already have, and the risk is identical everywhere: a
fluent number nobody checked. This server puts the gate where the drafting
happens, so any assistant can check a draft against the publishable figures
before a human ever reads it.

What it is
----------
JSON-RPC 2.0, one message per line, on stdin and stdout. No socket, no port, no
network of its own, and no dependency: the transport is newline-delimited JSON
over two file objects, which the standard library already provides, so the
default install gains this command without gaining a package. That keeps the
"zero runtime dependencies" property the README states, which an optional extra
would have qualified.

What it deliberately is not
---------------------------
Read-only, and structurally so rather than by intention. ``TOOLS`` is the whole
surface; a name outside it is refused before any handler runs, and there is no
handler that writes a file, exports a report, or records an approval. ``run``
with human sign-off remains the only path to an export, and nothing here can
stand in for it.

Every tool answers from the **publishable** figure set -- what ``run`` would
export, after suppression -- so a withheld cell comes back as the redaction
marker with a null value, never as the number it hides. The pre-suppression
figures are reachable in exactly one place, ``audit_narrative``, and only as the
*classifier* that lets a disclosed span be named as a disclosure; no display or
value from that set is ever put in a response. The distinction matters: a
disclosure response echoes the number the client itself sent, which is not the
server disclosing anything, while a figure listing that carried a raw withheld
value would be.

Nothing narrative is logged. A tool's arguments carry the author's draft, so the
error path names the tool and the exception type and nothing else; there is no
log level that turns the text back on.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from outcome_receipts.grounding import audit_narrative
from outcome_receipts.models import Figure, NumericSpan, SuppressedSpan
from outcome_receipts.verify import VerifyResult, verify_manifest

#: The MCP revision this server implements and declares at ``initialize``.
#: Single-sourced so the handshake, the documentation and the tests cannot
#: drift; bump it here and nowhere else when the revision moves.
PROTOCOL_VERSION = "2025-06-18"

SERVER_NAME = "outcome-receipts"

# JSON-RPC 2.0 error codes, by name rather than by magic number at the call site.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602

#: Resolves a spec path to ``(publishable, withheld)``. Injected rather than
#: imported so this module never reaches into the CLI: the computation lives
#: where the CLI already does it, and this module stays a transport plus four
#: read-only projections of a figure set.
FigureResolver = Callable[[str], tuple[Sequence[Figure], Sequence[Figure]]]


class ToolError(Exception):
    """A tool could not answer, with a reason safe to put on the wire.

    The message is composed by the raising code from names and identifiers, not
    from the caller's arguments, because a tool's arguments are the author's
    draft.
    """


@dataclass(frozen=True)
class Tool:
    """One read-only tool: its schema, and the function that answers it."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[Mapping[str, Any], FigureResolver], dict[str, Any]]


def _require_str(arguments: Mapping[str, Any], field: str) -> str:
    """One required string argument, or a refusal that does not quote it.

    A missing field is named; a wrong-typed field is named with its *type* and
    never with its value, because the value may be the draft.
    """

    value = arguments.get(field)
    if value is None:
        raise ToolError(f"missing required argument {field!r}")
    if not isinstance(value, str):
        raise ToolError(f"argument {field!r} must be a string, got {type(value).__name__}")
    return value


def _figure_payload(figure: Figure) -> dict[str, Any]:
    """One publishable figure, as a drafting tool needs to see it.

    ``value`` and ``display`` are read off the *post-suppression* figure, so a
    withheld cell arrives here already carrying ``None`` and the redaction
    marker. Nothing in this function un-suppresses anything; there is no branch
    that could, because the raw figure is not in scope.
    """

    return {
        "metric_id": figure.metric_id,
        "display": figure.display,
        "value": figure.value,
        "unit": figure.receipt.unit,
        "kind": figure.receipt.kind,
        "definition": figure.receipt.definition,
        "indicator": figure.receipt.indicator,
        "caveat": figure.receipt.caveat,
        "suppressed": figure.receipt.suppressed,
    }


def _span_payload(span: NumericSpan) -> dict[str, Any]:
    return {"text": span.text, "start": span.start, "end": span.end}


def _suppressed_span_payload(disclosure: SuppressedSpan) -> dict[str, Any]:
    """A disclosed protected cell.

    ``text`` is the client's own span, echoed back at the offsets it sent, and
    ``metric_ids`` names the metric rather than stating its value. The withheld
    figure's display is not in this payload and must not be added to it.
    """

    return {
        **_span_payload(disclosure.span),
        "metric_ids": list(disclosure.metric_ids),
        "publishable_metric_ids": list(disclosure.publishable_metric_ids),
        "ambiguous": disclosure.ambiguous,
    }


def _verify_payload(result: VerifyResult) -> dict[str, Any]:
    """The verify result, in the shape ``receipts verify --json`` emits.

    The counts are deliberately the same six the CLI reports, including the
    distinction between checks and *receipt* checks that a manifest descriptor
    would otherwise inflate. ``tests/test_mcp_server.py`` asserts this payload
    against the CLI's own JSON for the same inputs, so the two cannot drift
    apart quietly.
    """

    return {
        "command": "verify",
        "mode": "manifest",
        "ok": result.ok,
        "checks": [
            {
                "metric_id": check.metric_id,
                "ok": check.ok,
                "detail": check.detail,
                "kind": check.kind,
            }
            for check in result.checks
        ],
        "n_ok": result.n_ok,
        "drift": len(result.checks) - result.n_ok,
        "receipts_checked": len(result.receipt_checks),
        "receipts_ok": result.n_receipts_ok,
        "receipts_drift": len(result.failed_receipts),
        "manifest_checks": len(result.manifest_checks),
        "manifest_checks_failed": len(result.failed_manifest_checks),
    }


# --- the four tools --------------------------------------------------------


def _tool_list_publishable_figures(
    arguments: Mapping[str, Any], resolve: FigureResolver
) -> dict[str, Any]:
    publishable, _withheld = resolve(_require_str(arguments, "config"))
    return {"figures": [_figure_payload(figure) for figure in publishable]}


def _tool_audit_narrative(arguments: Mapping[str, Any], resolve: FigureResolver) -> dict[str, Any]:
    config = _require_str(arguments, "config")
    text = _require_str(arguments, "text")
    publishable, withheld = resolve(config)
    result = audit_narrative(text, publishable, withheld)
    return {
        "command": "audit",
        "ok": result.ok,
        "total": result.total,
        "bound": len(result.bound),
        "suppressed": [_suppressed_span_payload(item) for item in result.suppressed],
        "unbound": [_span_payload(span) for span in result.unbound],
    }


def _tool_verify_receipts(arguments: Mapping[str, Any], resolve: FigureResolver) -> dict[str, Any]:
    config = _require_str(arguments, "config")
    receipts = _require_str(arguments, "receipts")
    publishable, _withheld = resolve(config)
    try:
        manifest = json.loads(Path(receipts).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolError(f"could not read a receipts manifest at {receipts!r}") from exc
    if not isinstance(manifest, dict):
        raise ToolError(f"{receipts!r} is not a receipts manifest object")
    return _verify_payload(verify_manifest(publishable, manifest))


def _tool_trace_figure(arguments: Mapping[str, Any], resolve: FigureResolver) -> dict[str, Any]:
    """One figure's receipt: how the number was produced.

    A suppressed figure has no numerics to trace -- its receipt carries ``None``
    for value, row count, slice hash and columns, by construction -- so what
    comes back is the definition and the marker. The query is included because
    it is the definition of the figure, and a query is not a value; the *rows*
    it selected are not reachable from here at all.
    """

    config = _require_str(arguments, "config")
    metric_id = _require_str(arguments, "metric_id")
    publishable, _withheld = resolve(config)
    matches = [figure for figure in publishable if figure.metric_id == metric_id]
    if not matches:
        known = ", ".join(sorted(figure.metric_id for figure in publishable))
        raise ToolError(f"no publishable figure {metric_id!r}; this report publishes: {known}")
    figure = matches[0]
    return {
        **_figure_payload(figure),
        "value_sql": figure.receipt.value_sql,
        "row_count": figure.receipt.row_count,
        "slice_hash": figure.receipt.slice_hash,
        "column_names": (
            None if figure.receipt.column_names is None else list(figure.receipt.column_names)
        ),
        "data_source": figure.receipt.data_source,
        "collection_frequency": figure.receipt.collection_frequency,
        "computed_at": figure.receipt.computed_at,
    }


_CONFIG_PROPERTY = {"type": "string", "description": "path to the report spec TOML"}

#: The whole surface. A name that is not a key here is refused before any
#: handler runs, and there is no entry that writes, exports, approves, or
#: reaches a network. `tests/test_mcp_server.py` pins the key set, so adding a
#: tool is a deliberate change to a test rather than an unnoticed one.
TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        Tool(
            name="list_publishable_figures",
            description=(
                "Every figure this report may publish, after small-cell suppression: "
                "display, value, unit, kind, definition and whether it is withheld. "
                "A withheld cell carries the redaction marker and a null value."
            ),
            input_schema={
                "type": "object",
                "properties": {"config": _CONFIG_PROPERTY},
                "required": ["config"],
                "additionalProperties": False,
            },
            handler=_tool_list_publishable_figures,
        ),
        Tool(
            name="audit_narrative",
            description=(
                "Run the grounding gate over drafted text against the publishable "
                "figures. Returns bound spans, unbound spans, and spans that state a "
                "cell suppression withholds. Draft first, then audit; a number that "
                "does not bind must be removed or written as the receipt writes it."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "config": _CONFIG_PROPERTY,
                    "text": {"type": "string", "description": "the drafted narrative to check"},
                },
                "required": ["config", "text"],
                "additionalProperties": False,
            },
            handler=_tool_audit_narrative,
        ),
        Tool(
            name="verify_receipts",
            description=(
                "Re-derive every receipt in an exported receipts manifest from the spec "
                "and the data, and report any drift."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "config": _CONFIG_PROPERTY,
                    "receipts": {"type": "string", "description": "path to receipts.json"},
                },
                "required": ["config", "receipts"],
                "additionalProperties": False,
            },
            handler=_tool_verify_receipts,
        ),
        Tool(
            name="trace_figure",
            description=(
                "How one publishable figure was produced: its definition, unit, query, "
                "row count and slice hash. A withheld figure traces to the marker and "
                "its definition; it has no numerics to trace."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "config": _CONFIG_PROPERTY,
                    "metric_id": {"type": "string", "description": "the metric to trace"},
                },
                "required": ["config", "metric_id"],
                "additionalProperties": False,
            },
            handler=_tool_trace_figure,
        ),
    )
}


# --- JSON-RPC ---------------------------------------------------------------


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _result(request_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def _initialize_result() -> dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        # Tools only. No `resources`, no `prompts`, and in particular no
        # `sampling`: a server that could ask the client's model a question
        # would be a second path to a number, which is the one thing this
        # project does not have.
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": SERVER_NAME, "version": _version()},
    }


def _version() -> str:
    from outcome_receipts import __version__

    return __version__


def _tools_list_result() -> dict[str, Any]:
    return {
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            }
            for tool in TOOLS.values()
        ]
    }


def _call_tool(params: Mapping[str, Any], resolve: FigureResolver) -> dict[str, Any]:
    """Dispatch one ``tools/call``, refusing anything not in ``TOOLS``.

    An unknown name is a protocol error, not a tool result: answering it as a
    result with ``isError`` would let a client that only reads ``content`` treat
    "there is no such tool" as an answer from one.
    """

    name = params.get("name")
    if not isinstance(name, str):
        raise ToolError("tools/call requires a string 'name'")
    tool = TOOLS.get(name)
    if tool is None:
        known = ", ".join(sorted(TOOLS))
        raise ToolError(f"no tool {name!r}; this server exposes: {known}")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, Mapping):
        raise ToolError(f"tool {name!r} requires an 'arguments' object")
    payload = tool.handler(arguments, resolve)
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2, sort_keys=True)}],
        "structuredContent": payload,
        "isError": False,
    }


def handle(message: Mapping[str, Any], resolve: FigureResolver) -> dict[str, Any] | None:
    """Answer one JSON-RPC message, or ``None`` for a notification.

    A notification (no ``id``) gets no response, per JSON-RPC 2.0. That is not a
    detail: ``notifications/initialized`` is a notification, and answering it
    breaks the handshake with clients that are waiting on the next request.
    """

    request_id = message.get("id")
    method = message.get("method")
    if not isinstance(method, str):
        return _error(request_id, INVALID_REQUEST, "message has no method")
    is_notification = "id" not in message

    if method == "initialize":
        result = _initialize_result()
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = _tools_list_result()
    elif method == "tools/call":
        params = message.get("params") or {}
        if not isinstance(params, Mapping):
            return None if is_notification else _error(request_id, INVALID_PARAMS, "params")
        try:
            result = _call_tool(params, resolve)
        except ToolError as exc:
            return None if is_notification else _error(request_id, INVALID_PARAMS, str(exc))
    elif method.startswith("notifications/"):
        return None
    else:
        return None if is_notification else _error(request_id, METHOD_NOT_FOUND, method)

    return None if is_notification else _result(request_id, result)


def serve(stream_in: IO[str], stream_out: IO[str], resolve: FigureResolver) -> int:
    """Read messages until end of input, answering each on ``stream_out``.

    Every response is flushed as it is written, because a client blocks on the
    answer to the request it just sent and a buffered stdout would deadlock the
    handshake. The loop never raises out: a handler failure becomes a JSON-RPC
    error naming the exception *type*, so a crash cannot take the exception's
    message -- which may quote the author's draft -- onto any stream.
    """

    for line in stream_in:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            message = json.loads(stripped)
        except json.JSONDecodeError:
            _write(stream_out, _error(None, PARSE_ERROR, "message is not valid JSON"))
            continue
        if not isinstance(message, Mapping):
            _write(stream_out, _error(None, INVALID_REQUEST, "message is not an object"))
            continue
        # Broad on purpose. One malformed call must not take the session down:
        # a client that lost its server mid-conversation has no way to tell a
        # crash from a refusal, and would have to be restarted to find out.
        try:
            response = handle(message, resolve)
        except Exception as exc:
            response = _error(
                message.get("id"),
                INVALID_PARAMS,
                f"{message.get('method')!r} failed: {type(exc).__name__}",
            )
        if response is not None:
            _write(stream_out, response)
    return 0


def _write(stream_out: IO[str], payload: Mapping[str, Any]) -> None:
    stream_out.write(json.dumps(payload) + "\n")
    stream_out.flush()
