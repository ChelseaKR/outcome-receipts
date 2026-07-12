from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from outcome_receipts.cli import EXIT_VERIFY_FAIL, main
from outcome_receipts.config import load_spec
from outcome_receipts.grounding import ground
from outcome_receipts.model_draft import (
    BedrockDrafter,
    DraftingPolicyError,
    build_narrative_drafter,
)
from outcome_receipts.models import DraftingSpec, Figure, Receipt


def _figure() -> Figure:
    receipt = Receipt("clients", "SELECT 12", 12, "0" * 64, 12.0, "count", "fixed")
    return Figure("clients", 12.0, "12", receipt)


class FakeClient:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        return {"output": {"message": {"content": [{"text": self.text}]}}}


def test_cloud_drafting_requires_config_and_cli_authorization() -> None:
    policy = DraftingSpec(provider="bedrock", enabled=True, model_id="anthropic.claude")
    with pytest.raises(DraftingPolicyError, match="allow-cloud-drafting"):
        build_narrative_drafter(policy, allow_cloud=False)
    assert build_narrative_drafter(DraftingSpec(), allow_cloud=True) is None


def test_bedrock_receives_only_filled_narrative_and_display_allowlist() -> None:
    client = FakeClient("We served 12 clients.")
    drafter = BedrockDrafter("anthropic.claude", client=client)
    narrative = drafter.draft("We served {clients} clients.", [_figure()])
    assert narrative == "We served 12 clients."
    call = client.calls[0]
    prompt = str(call["messages"])
    assert "ALLOWLIST: 12" in prompt
    assert "SELECT 12" not in prompt
    assert ground(narrative, [_figure()]).ok


def test_model_invented_number_is_blocked_by_the_same_gate() -> None:
    drafter = BedrockDrafter("anthropic.claude", client=FakeClient("We served 12 plus 999."))
    result = ground(drafter.draft("We served {clients}.", [_figure()]), [_figure()])
    assert not result.ok
    assert [span.text for span in result.unbound] == ["999"]


def test_bedrock_policy_parses_and_cli_fails_without_run_authorization(tmp_path: Path) -> None:
    (tmp_path / "data.csv").write_text("client_id\nC1\n", encoding="utf-8")
    config = tmp_path / "report.toml"
    config.write_text(
        """[data]
path = "data.csv"
[report]
title = "Test"
template = "Served {clients}."
[report.drafting]
provider = "bedrock"
enabled = true
model_id = "anthropic.claude"
[metrics.clients]
description = "Clients"
definition = "Rows."
value_sql = "SELECT COUNT(*) FROM data"
slice_sql = "SELECT * FROM data"
""",
        encoding="utf-8",
    )
    assert load_spec(config).report.drafting.model_id == "anthropic.claude"
    assert main(["run", "--config", str(config), "--out", str(tmp_path / "out")]) == (
        EXIT_VERIFY_FAIL
    )
    assert not (tmp_path / "out").exists()
