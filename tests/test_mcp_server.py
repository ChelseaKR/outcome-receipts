"""The read-only MCP server: what it exposes, and what it can never say.

Issue 163. The tests are grouped by the four "Done when" bullets plus the two
properties that make putting the gate inside a drafting tool safe at all:

1. There is no write surface. Not "no write surface is documented" -- ``TOOLS``
   is the whole dispatch table, a name outside it never reaches a handler, and
   the key set is pinned here so adding one is a deliberate edit to this file.
2. A withheld cell cannot come back as its value. The sentinel below hands the
   server a withheld figure whose raw display is a token that appears nowhere
   else, then reads every byte of every response looking for it.
"""

from __future__ import annotations

import io
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from outcome_receipts.claims import DirectionEvidence
from outcome_receipts.cli import (
    _compute_all,
    _direction_evidence,
    _publishable_and_hidden,
    main,
)
from outcome_receipts.mcp import (
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    PROTOCOL_VERSION,
    TOOLS,
    FigureResolver,
    serve,
)
from outcome_receipts.models import REDACTED_DISPLAY, Figure, Receipt

ROOT = Path(__file__).resolve().parents[1]
DEMO = str(ROOT / "examples" / "housing-demo" / "report.toml")

#: A raw withheld display that appears nowhere else in the project, so finding
#: it in a response can only mean it came out of the withheld figure set.
SENTINEL_VALUE = 424242.0
SENTINEL_DISPLAY = "424,242"


def _demo_resolver(
    config: str,
) -> tuple[Sequence[Figure], Sequence[Figure], Sequence[DirectionEvidence]]:
    _spec, _rows, figures, comparison, reconciliation = _compute_all(
        config, reproducible=True, quiet=True
    )
    publishable, hidden = _publishable_and_hidden(figures)
    evidence = _direction_evidence(
        comparison, reconciliation, [figure.metric_id for figure in hidden]
    )
    return publishable, hidden, evidence


def _exchange(
    messages: Sequence[dict[str, Any]], resolve: FigureResolver = _demo_resolver
) -> list[dict[str, Any]]:
    """Drive the server over an in-memory pair of streams and collect responses."""

    stream_in = io.StringIO("\n".join(json.dumps(message) for message in messages) + "\n")
    stream_out = io.StringIO()
    assert serve(stream_in, stream_out, resolve) == 0
    return [json.loads(line) for line in stream_out.getvalue().splitlines() if line.strip()]


def _call(
    name: str, arguments: dict[str, Any], resolve: FigureResolver = _demo_resolver
) -> dict[str, Any]:
    (response,) = _exchange(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        ],
        resolve,
    )
    return response


def _structured(response: dict[str, Any]) -> dict[str, Any]:
    result = response["result"]
    payload = result["structuredContent"]
    # The text block and the structured block must be the same object, or a
    # client that reads only one of them is reading something the other does
    # not say.
    assert json.loads(result["content"][0]["text"]) == payload
    assert result["isError"] is False
    return dict(payload)


# --- "Done when": the same bound/unbound result as `audit --json` -----------


def test_audit_over_mcp_matches_the_cli_json_payload_exactly(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """One contract, two implementations, held equal by this assertion.

    ``mcp.py`` deliberately does not import the CLI's private payload builders
    (that would be an import cycle), so the two serialisations are separate
    code. This is what stops them drifting: the CLI's own JSON is the expected
    value, so a field added on one side and not the other turns this red.
    """

    text = "We served 12 clients and it was a good year."
    narrative = tmp_path / "draft.md"
    narrative.write_text(text, encoding="utf-8")

    assert (
        main(["audit", "--config", DEMO, "--narrative", str(narrative), "--reproducible", "--json"])
        == 0
    )
    from_cli = json.loads(capsys.readouterr().out)

    from_mcp = _structured(_call("audit_narrative", {"config": DEMO, "text": text}))
    assert from_mcp == from_cli


def test_verify_over_mcp_matches_the_cli_json_payload_exactly(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    out = tmp_path / "out"
    assert (
        main(
            [
                "run",
                "--config",
                DEMO,
                "--out",
                str(out),
                "--reproducible",
                "--approved-by",
                "A. Reviewer",
            ]
        )
        == 0
    )
    receipts = out / "receipts.json"
    capsys.readouterr()

    assert (
        main(["verify", "--config", DEMO, "--receipts", str(receipts), "--reproducible", "--json"])
        == 0
    )
    from_cli = json.loads(capsys.readouterr().out)

    from_mcp = _structured(_call("verify_receipts", {"config": DEMO, "receipts": str(receipts)}))
    assert from_mcp == from_cli
    assert from_mcp["ok"] is True


def test_an_audit_that_discloses_a_withheld_cell_reports_it_as_a_disclosure() -> None:
    """The category that distinguishes `audit` from plain grounding survives.

    The span echoed back is the client's own text at its own offsets, and the
    metric is named rather than valued -- that is why the withheld set may be
    consulted here at all.
    """

    payload = _structured(
        _call("audit_narrative", {"config": DEMO, "text": "Only 6 people moved on."})
    )

    assert payload["ok"] is False
    (disclosure,) = payload["suppressed"]
    assert disclosure["metric_ids"] == ["exits_permanent"]
    assert disclosure["text"] == "6"


# --- "Done when": a withheld figure returns the marker, never the value -----


def _sentinel_resolver(
    _config: str,
) -> tuple[Sequence[Figure], Sequence[Figure], Sequence[DirectionEvidence]]:
    """Publishable figures plus one withheld figure carrying a unique display.

    The withheld figure's *raw* form is what a leak would expose, so it is the
    thing given the distinctive value. Its publishable counterpart is redacted
    exactly as ``suppress_figures`` would leave it.
    """

    def figure(metric_id: str, value: float | None, display: str, *, suppressed: bool) -> Figure:
        return Figure(
            metric_id=metric_id,
            value=value,
            display=display,
            receipt=Receipt(
                metric_id=metric_id,
                value_sql="SELECT COUNT(*) FROM data",
                row_count=None if suppressed else 3,
                slice_hash=None if suppressed else "a" * 64,
                value=None if suppressed else value,
                unit="count",
                computed_at="2026-01-01T00:00:00Z",
                definition="how the figure is defined",
                suppressed=suppressed,
            ),
        )

    publishable = [
        figure("served", 12.0, "12", suppressed=False),
        figure("tiny", None, REDACTED_DISPLAY, suppressed=True),
    ]
    withheld = [figure("tiny", SENTINEL_VALUE, SENTINEL_DISPLAY, suppressed=False)]
    return publishable, withheld, ()


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("list_publishable_figures", {"config": "spec.toml"}),
        ("trace_figure", {"config": "spec.toml", "metric_id": "tiny"}),
        ("audit_narrative", {"config": "spec.toml", "text": "We served 12 and also 999."}),
    ],
)
def test_no_response_can_carry_the_withheld_figures_raw_value(
    tool: str, arguments: dict[str, Any]
) -> None:
    """The sentinel.

    Every tool is driven against a figure set whose withheld member carries
    ``424,242`` -- a token that exists nowhere else in this project -- and the
    whole response is searched as raw bytes. A substring search over the served
    demo would be meaningless (a withheld ``6`` matches an offset), so the
    fixture is built to make the search decisive.
    """

    response = _call(tool, arguments, _sentinel_resolver)
    raw = json.dumps(response)

    assert SENTINEL_DISPLAY not in raw
    assert "424242" not in raw
    assert str(SENTINEL_VALUE) not in raw


def test_tracing_a_withheld_figure_returns_the_marker_and_no_numerics() -> None:
    payload = _structured(
        _call("trace_figure", {"config": "spec.toml", "metric_id": "tiny"}, _sentinel_resolver)
    )

    assert payload["suppressed"] is True
    assert payload["display"] == REDACTED_DISPLAY
    assert payload["value"] is None
    assert payload["row_count"] is None
    assert payload["slice_hash"] is None
    # The definition still travels: a reader has to be able to tell a withheld
    # cell from a metric that does not exist.
    assert payload["definition"] == "how the figure is defined"


def test_listing_figures_marks_the_withheld_one_and_states_no_value() -> None:
    payload = _structured(
        _call("list_publishable_figures", {"config": "spec.toml"}, _sentinel_resolver)
    )

    by_id = {item["metric_id"]: item for item in payload["figures"]}
    assert by_id["served"]["value"] == 12.0
    assert by_id["tiny"]["suppressed"] is True
    assert by_id["tiny"]["display"] == REDACTED_DISPLAY
    assert by_id["tiny"]["value"] is None


def test_tracing_a_metric_the_report_does_not_publish_is_refused_by_name() -> None:
    response = _call("trace_figure", {"config": DEMO, "metric_id": "no_such_metric"})

    assert response["error"]["code"] == INVALID_PARAMS
    assert "no publishable figure 'no_such_metric'" in response["error"]["message"]


# --- "Done when": there is no write tool, and an unknown name is refused ----


def test_the_exposed_surface_is_exactly_the_four_read_only_tools() -> None:
    """Pinned deliberately.

    Deriving the expected set from ``TOOLS`` would assert nothing; typing it out
    means a fifth tool cannot arrive without someone editing this line.
    """

    assert sorted(TOOLS) == [
        "audit_narrative",
        "list_publishable_figures",
        "trace_figure",
        "verify_receipts",
    ]


@pytest.mark.parametrize(
    "name", ["run", "export", "export_report", "approve", "write_report", "receipts.run", ""]
)
def test_a_tool_name_that_is_not_exposed_is_refused_before_any_handler_runs(name: str) -> None:
    response = _call(name, {"config": DEMO})

    assert "result" not in response
    assert response["error"]["code"] == INVALID_PARAMS
    assert f"no tool {name!r}" in response["error"]["message"]


def test_tools_list_advertises_a_schema_for_every_tool_and_no_others() -> None:
    (response,) = _exchange([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])

    advertised = response["result"]["tools"]
    assert [tool["name"] for tool in advertised] == list(TOOLS)
    for tool in advertised:
        assert tool["description"]
        assert tool["inputSchema"]["type"] == "object"
        assert "config" in tool["inputSchema"]["properties"]
        assert tool["inputSchema"]["additionalProperties"] is False


# --- the handshake and the transport ---------------------------------------


def test_initialize_declares_the_protocol_version_and_tools_only() -> None:
    (response,) = _exchange([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}])

    result = response["result"]
    assert result["protocolVersion"] == PROTOCOL_VERSION
    assert result["serverInfo"]["name"] == "outcome-receipts"
    # No `sampling` capability. A server that could ask the client's model a
    # question would be a second path to a number.
    assert set(result["capabilities"]) == {"tools"}


def test_a_notification_gets_no_response_at_all() -> None:
    """``notifications/initialized`` carries no id, and answering it hangs clients."""

    responses = _exchange(
        [
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 7, "method": "ping"},
        ]
    )

    assert [response["id"] for response in responses] == [7]


def test_an_unknown_method_is_a_method_not_found_error() -> None:
    (response,) = _exchange([{"jsonrpc": "2.0", "id": 1, "method": "resources/list"}])

    assert response["error"]["code"] == METHOD_NOT_FOUND


def test_a_malformed_line_is_refused_and_the_session_continues() -> None:
    """One bad message must not end the session.

    A client that lost its server mid-conversation cannot tell a crash from a
    refusal; it has to restart to find out. So the loop answers and keeps going.
    """

    stream_in = io.StringIO(
        "not json\n\n[1, 2, 3]\n" + json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping"}) + "\n"
    )
    stream_out = io.StringIO()
    assert serve(stream_in, stream_out, _demo_resolver) == 0

    responses = [json.loads(line) for line in stream_out.getvalue().splitlines()]
    assert responses[0]["error"]["code"] == PARSE_ERROR
    assert responses[1]["error"]["code"] == -32600
    assert responses[2]["id"] == 9 and "result" in responses[2]


@pytest.mark.parametrize(
    ("tool", "arguments", "match"),
    [
        ("audit_narrative", {"config": DEMO}, "missing required argument 'text'"),
        ("audit_narrative", {"config": DEMO, "text": 5}, "must be a string, got int"),
        ("list_publishable_figures", {}, "missing required argument 'config'"),
    ],
)
def test_a_missing_or_wrong_typed_argument_is_named_without_quoting_its_value(
    tool: str, arguments: dict[str, Any], match: str
) -> None:
    response = _call(tool, arguments)

    assert response["error"]["code"] == INVALID_PARAMS
    assert match in response["error"]["message"]


def test_a_handler_that_raises_reports_the_exception_type_and_not_the_draft() -> None:
    """The draft is in the arguments, so it must not reach an error message.

    A resolver that raises with the narrative in its message stands in for any
    future handler bug: what comes back names the method and the exception
    class, and carries nothing the client sent.
    """

    draft = "the author's confidential draft about 1,234 households"

    def exploding(
        _config: str,
    ) -> tuple[Sequence[Figure], Sequence[Figure], Sequence[DirectionEvidence]]:
        raise RuntimeError(draft)

    response = _call("audit_narrative", {"config": DEMO, "text": draft}, exploding)

    message = response["error"]["message"]
    assert "RuntimeError" in message
    assert "tools/call" in message
    assert draft not in message
    assert "1,234" not in message


def test_the_server_writes_nothing_but_json_rpc_to_its_output_stream() -> None:
    """stdout is the transport. One stray print corrupts every client."""

    stream_in = io.StringIO(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "audit_narrative",
                    "arguments": {"config": DEMO, "text": "We served 12 clients."},
                },
            }
        )
        + "\n"
    )
    stream_out = io.StringIO()
    serve(stream_in, stream_out, _demo_resolver)

    for line in stream_out.getvalue().splitlines():
        assert json.loads(line)["jsonrpc"] == "2.0"


# --- "Done when": the default install is unchanged -------------------------


def test_the_server_adds_no_runtime_dependency() -> None:
    """The issue proposed an optional extra; the standard library was enough.

    Requiring a package to run the server would have qualified the "zero runtime
    dependencies" claim the README makes, for a transport that is newline
    JSON over two file objects.
    """

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "\ndependencies = []\n" in pyproject
    source = (ROOT / "src" / "outcome_receipts" / "mcp.py").read_text(encoding="utf-8")
    for third_party in ("import boto3", "import mcp", "from mcp ", "import anyio", "import httpx"):
        assert third_party not in source


# --- the refusals, exercised rather than assumed ---------------------------


def test_a_receipts_path_that_is_not_a_manifest_is_refused(tmp_path: Path) -> None:
    """Three ways the path can be wrong, and none of them may become a pass.

    A verify that could not read its manifest must not report `ok`. This is the
    portfolio's dominant defect in its verification shape: a failed read
    published as a clean result.
    """

    missing = tmp_path / "nope.json"
    not_json = tmp_path / "not.json"
    not_json.write_text("{{{", encoding="utf-8")
    not_object = tmp_path / "list.json"
    not_object.write_text("[]", encoding="utf-8")

    for path, match in (
        (missing, "could not read a receipts manifest"),
        (not_json, "could not read a receipts manifest"),
        (not_object, "is not a receipts manifest object"),
    ):
        response = _call("verify_receipts", {"config": DEMO, "receipts": str(path)})
        assert "result" not in response, f"{path.name} produced a result"
        assert response["error"]["code"] == INVALID_PARAMS
        assert match in response["error"]["message"]


@pytest.mark.parametrize(
    ("message", "code", "match"),
    [
        ({"jsonrpc": "2.0", "id": 1}, -32600, "message has no method"),
        ({"jsonrpc": "2.0", "id": 1, "method": 7}, -32600, "message has no method"),
        (
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": ["nope"]},
            INVALID_PARAMS,
            "params",
        ),
        (
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": 7}},
            INVALID_PARAMS,
            "requires a string 'name'",
        ),
        (
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "audit_narrative", "arguments": "text"},
            },
            INVALID_PARAMS,
            "requires an 'arguments' object",
        ),
    ],
)
def test_a_malformed_request_is_refused_with_a_named_reason(
    message: dict[str, Any], code: int, match: str
) -> None:
    (response,) = _exchange([message])

    assert "result" not in response
    assert response["error"]["code"] == code
    assert match in response["error"]["message"]


def test_a_malformed_tools_call_notification_still_gets_no_response() -> None:
    """No id means no reply, even when the call itself is unanswerable.

    Replying to a notification desynchronises a client that is counting
    responses, and an error reply is no more welcome than a result.
    """

    responses = _exchange(
        [
            {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "no_such_tool"}},
            {"jsonrpc": "2.0", "method": "tools/call", "params": ["not an object"]},
            {"jsonrpc": "2.0", "method": "definitely/unknown"},
            {"jsonrpc": "2.0", "id": 11, "method": "ping"},
        ]
    )

    assert [response["id"] for response in responses] == [11]
