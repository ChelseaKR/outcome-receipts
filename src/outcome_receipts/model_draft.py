"""Policy-gated optional Claude-on-Bedrock narrative drafting seam."""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from typing import Protocol, cast

from outcome_receipts.draft import draft_template
from outcome_receipts.models import DraftingSpec, Figure


class DraftingPolicyError(ValueError):
    """Cloud drafting was configured but not explicitly authorized for this run."""


class ConverseClient(Protocol):
    def converse(self, **kwargs: object) -> dict[str, object]:
        raise NotImplementedError


class NarrativeDrafter(Protocol):
    def draft(self, template: str, figures: Sequence[Figure]) -> str:
        raise NotImplementedError


class BedrockDrafter:
    """Send only the filled template and receipted display allowlist to Bedrock."""

    def __init__(
        self, model_id: str, *, max_tokens: int = 1200, client: ConverseClient | None = None
    ) -> None:
        self.model_id = model_id
        self.max_tokens = max_tokens
        self._injected_client = client

    def _client(self) -> ConverseClient:
        if self._injected_client is not None:
            return self._injected_client
        try:
            boto3 = importlib.import_module("boto3")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Bedrock drafting requires the optional 'bedrock' dependency"
            ) from exc
        return cast(ConverseClient, boto3.client("bedrock-runtime"))

    def draft(self, template: str, figures: Sequence[Figure]) -> str:
        baseline = draft_template(template, figures)
        displays = ", ".join(figure.display for figure in figures)
        prompt = (
            "Rewrite the supplied funder-report narrative for clarity. Do not add, remove, "
            "spell out, round, or alter any numeric claim. Use only numeric displays in the "
            f"allowlist.\nALLOWLIST: {displays}\nNARRATIVE:\n{baseline}"
        )
        response = self._client().converse(
            modelId=self.model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": self.max_tokens, "temperature": 0},
        )
        try:
            output = cast(dict[str, object], response["output"])
            message = cast(dict[str, object], output["message"])
            content = cast(list[dict[str, object]], message["content"])
            text = content[0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Bedrock returned no narrative text") from exc
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Bedrock returned no narrative text")
        return text.strip()


def build_narrative_drafter(
    policy: DraftingSpec, *, allow_cloud: bool, client: ConverseClient | None = None
) -> NarrativeDrafter | None:
    """Build the opted-in provider, or return the deterministic default seam."""

    if not policy.enabled or policy.provider == "deterministic":
        return None
    if not allow_cloud:
        raise DraftingPolicyError(
            "Bedrock drafting is enabled in config but this run lacks --allow-cloud-drafting"
        )
    return BedrockDrafter(policy.model_id, max_tokens=policy.max_tokens, client=client)
