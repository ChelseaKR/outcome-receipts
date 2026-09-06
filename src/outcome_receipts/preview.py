"""Preview what a suppression policy would withhold, before anything is exported.

Suppression is a policy decision with a primary source, and until now the only
way to see what a threshold does to a particular report was to run the report
and look at what came out. That is the wrong order: the consequences should be
visible *before* export, not after.

`preview_policies` computes the raw figures once and then replays
`suppress_figures` over that same raw set for each policy, so every policy is
measured against identical inputs. Nothing here writes a report, a chart, a
bundle, or a ledger entry.

**The shareable form never prints a withheld value.** The withheld values are
the entire point of the exercise, so a preview that printed them would hand a
reader exactly what suppression exists to remove -- and a preview is far more
likely to be pasted into a chat or an email than a report is. `--local` opts
into the values for the operator who already holds the data. The two forms are
built by one function with one flag, so the shareable form cannot drift into
carrying values by accident, and a sentinel test asserts no withheld value
appears in it.
"""

from __future__ import annotations

from dataclasses import dataclass

from outcome_receipts.models import Figure
from outcome_receipts.policy import SuppressionPolicy
from outcome_receipts.suppression import _disclosing_combination, suppress_figures

#: The metric_id suffix `comparison.py` gives a period-over-period delta.
_DELTA_SUFFIX = "__delta"


@dataclass(frozen=True, slots=True)
class CascadeEntry:
    """One complementary suppression, and the rule that caused it."""

    metric_id: str
    #: `delta`, `percent`, or `recovery` -- the three rules
    #: `suppression._complementary_suppress` runs to a fixed point.
    rule: str
    #: For the recovery rule, the still-visible figures whose signed
    #: combination would have rebuilt a withheld cell. Empty for the other two,
    #: whose trigger is structural rather than arithmetic.
    disclosing_combination: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PolicyPreview:
    """What one policy would do to one report's figures."""

    policy: SuppressionPolicy
    primary_suppressed: tuple[str, ...]
    complementary: tuple[CascadeEntry, ...]
    surviving: tuple[str, ...]
    #: metric_id -> pre-suppression value, for every figure that would be
    #: withheld. Populated always; rendered only in the local profile.
    withheld_values: tuple[tuple[str, float], ...]

    @property
    def withheld_total(self) -> int:
        return len(self.primary_suppressed) + len(self.complementary)

    @property
    def surviving_total(self) -> int:
        """How many numbers would survive into the narrative."""
        return len(self.surviving)

    @property
    def percent_control_engaged(self) -> bool:
        return any(entry.rule == "percent" for entry in self.complementary)

    @property
    def comparison_control_engaged(self) -> bool:
        return any(entry.rule == "delta" for entry in self.complementary)

    @property
    def recovery_control_engaged(self) -> bool:
        return any(entry.rule == "recovery" for entry in self.complementary)


def _classify_cascade(
    metric_id: str,
    figures: list[Figure],
    primary: set[str],
    withheld: set[str],
) -> CascadeEntry:
    """Attribute one complementary suppression to the rule that produced it.

    Read-only re-derivation. `suppression._complementary_suppress` runs its
    three rules to a shared fixed point and returns only the resulting id set,
    so the rule that fired is recovered here by testing the same conditions
    against the same raw figures rather than by changing the privacy engine to
    report them. The three tests are mutually exclusive in the order applied,
    which mirrors the order the engine applies them.
    """
    units = {figure.metric_id: figure.receipt.unit for figure in figures}
    values = {figure.metric_id: figure.value for figure in figures if figure.value is not None}

    if metric_id.endswith(_DELTA_SUFFIX):
        base = metric_id[: -len(_DELTA_SUFFIX)]
        if any(other.startswith(base) and other in withheld for other in values):
            return CascadeEntry(metric_id, "delta", ())

    if units.get(metric_id) == "percent":
        return CascadeEntry(metric_id, "percent", ())

    # The recovery rule: this figure was taken because some withheld cell could
    # be rebuilt from a set of visible same-unit figures that included it. Name
    # the combination for the smallest withheld cell it can still reconstruct.
    unit = units.get(metric_id)
    visible = [
        (other, value)
        for other, value in sorted(values.items())
        if other not in withheld and units.get(other) == unit
    ]
    visible.append((metric_id, values.get(metric_id, 0.0)))
    for target_id in sorted(primary, key=lambda item: (abs(values.get(item, 0.0)), item)):
        if units.get(target_id) != unit:
            continue
        target = values.get(target_id)
        if target is None:
            continue
        combination = _disclosing_combination(target, visible)
        if combination is not None and metric_id in combination:
            return CascadeEntry(metric_id, "recovery", combination)
    return CascadeEntry(metric_id, "recovery", ())


def preview_policy(figures: list[Figure], policy: SuppressionPolicy) -> PolicyPreview:
    """Run one policy over a raw figure set without keeping the redacted output.

    `figures` must be raw: `suppress_figures` refuses an already-redacted set,
    which is what keeps a preview from being run over the output of another
    preview and reporting a false all-clear.
    """
    _redacted, result = suppress_figures(
        list(figures),
        threshold=policy.threshold,
        complementary_rule=policy.complementary_rule,
    )
    primary = set(result.suppressed)
    withheld = primary | set(result.complementary_suppressed)
    cascades = tuple(
        _classify_cascade(metric_id, figures, primary, withheld)
        for metric_id in result.complementary_suppressed
    )
    values = {figure.metric_id: figure.value for figure in figures if figure.value is not None}
    return PolicyPreview(
        policy=policy,
        primary_suppressed=result.suppressed,
        complementary=cascades,
        surviving=result.unsuppressed,
        withheld_values=tuple(
            (metric_id, values[metric_id]) for metric_id in sorted(withheld) if metric_id in values
        ),
    )


def preview_policies(
    figures: list[Figure], policies: list[SuppressionPolicy]
) -> list[PolicyPreview]:
    """Compute the raw figures once, then measure every policy against them."""
    return [preview_policy(figures, policy) for policy in policies]


def preview_payload(
    previews: list[PolicyPreview], *, include_withheld_values: bool
) -> dict[str, object]:
    """The JSON form. `include_withheld_values` is the only local-only switch."""
    return {
        "schema_version": "1.0",
        "kind": "suppression-preview",
        "wrote_nothing": True,
        "includes_withheld_values": include_withheld_values,
        "policies": [
            {
                "policy_id": preview.policy.policy_id,
                "threshold": preview.policy.threshold,
                "complementary_rule": preview.policy.complementary_rule,
                "cited": preview.policy.cited,
                "citation": preview.policy.citation or None,
                "citation_url": preview.policy.citation_url or None,
                "citation_read": preview.policy.citation_read or None,
                "primary_suppressed": list(preview.primary_suppressed),
                "complementary_suppressed": [
                    {
                        "metric_id": entry.metric_id,
                        "rule": entry.rule,
                        "disclosing_combination": list(entry.disclosing_combination),
                    }
                    for entry in preview.complementary
                ],
                "surviving": list(preview.surviving),
                "counts": {
                    "withheld": preview.withheld_total,
                    "surviving": preview.surviving_total,
                },
                "controls": {
                    "comparison_delta": preview.comparison_control_engaged,
                    "percentage": preview.percent_control_engaged,
                    "recovery": preview.recovery_control_engaged,
                },
                **(
                    {"withheld_values": dict(preview.withheld_values)}
                    if include_withheld_values
                    else {}
                ),
            }
            for preview in previews
        ],
    }


def render_preview_markdown(previews: list[PolicyPreview], *, include_withheld_values: bool) -> str:
    """The Markdown form, for an operator comparing policies side by side."""
    lines = [
        "# Suppression preview",
        "",
        "Nothing was written: no report, no charts, no bundle, no ledger entry.",
        "",
    ]
    if not include_withheld_values:
        lines.extend(
            [
                "Withheld values are not shown. This is the shareable profile; the",
                "withheld numbers are what suppression exists to remove. Re-run with",
                "`--local` to see them on a machine that already holds the data.",
                "",
            ]
        )
    lines.extend(
        [
            "| Policy | Threshold | Withheld | Surviving | Cited |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for preview in previews:
        lines.append(
            f"| `{preview.policy.policy_id}` | {preview.policy.threshold} | "
            f"{preview.withheld_total} | {preview.surviving_total} | "
            f"{'yes' if preview.policy.cited else 'no source'} |"
        )
    for preview in previews:
        lines.extend(
            [
                "",
                f"## `{preview.policy.policy_id}` at threshold {preview.policy.threshold}",
                "",
            ]
        )
        if preview.policy.cited:
            lines.extend(
                [
                    preview.policy.citation,
                    "",
                    f"<{preview.policy.citation_url}>",
                    "",
                    f"Read {preview.policy.citation_read}.",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "No citation: this threshold was supplied on the command line and",
                    "claims no source. Only a registered policy claims one.",
                    "",
                ]
            )
        primary = ", ".join(f"`{item}`" for item in preview.primary_suppressed) or "none"
        lines.extend([f"Primary-suppressed: {primary}", ""])
        if preview.complementary:
            lines.extend(["| Complementary | Rule | Disclosing combination |", "|---|---|---|"])
            for entry in preview.complementary:
                combination = (
                    " ± ".join(f"`{item}`" for item in entry.disclosing_combination) or "—"
                )
                lines.append(f"| `{entry.metric_id}` | {entry.rule} | {combination} |")
        else:
            lines.append("No complementary cascade fired.")
        lines.extend(
            [
                "",
                f"Controls engaged — comparison delta: "
                f"{'yes' if preview.comparison_control_engaged else 'no'}; "
                f"percentage: {'yes' if preview.percent_control_engaged else 'no'}; "
                f"recovery: {'yes' if preview.recovery_control_engaged else 'no'}.",
                "",
                f"{preview.surviving_total} number(s) would survive into the narrative.",
            ]
        )
        if include_withheld_values:
            lines.extend(["", "| Withheld metric | Value |", "|---|---:|"])
            for metric_id, value in preview.withheld_values:
                lines.append(f"| `{metric_id}` | {value:g} |")
    return "\n".join(lines) + "\n"
