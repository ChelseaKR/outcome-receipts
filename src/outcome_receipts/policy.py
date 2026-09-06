"""The registry of named small-cell suppression policies.

The threshold this tool ships is a policy choice with a primary source, not a
constant of nature, and the README already says the binding rule is the
operator's. A named policy makes that choice explicit, citable, and pinnable
from a spec, so a receipt can say *which* rule produced a withheld cell rather
than only that something was withheld.

**Why the registry has exactly one entry.**

`docs/audits/hud-coc-suppression-calibration-2026-08-21.md` established, against
real published HUD data, that HUD prescribes no numeric small-cell rule at all:
its own CoC-level Point-in-Time reports are published unsuppressed, down to and
including exact zeros, and its HMIS standards leave the numeric rule to local
policy. So there is no second *cited* policy to register. Inventing a
`hud-...` entry with a citation would fabricate a source, which is precisely
what this module exists to prevent.

An operator who wants to see the consequences of a different number therefore
supplies it directly, and gets an `ad_hoc_policy` that is labelled uncited and
carries no citation. That distinction is the point: a preview may explore any
threshold, but only a registered policy claims a source.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The policy id assumed when a spec pins none.
DEFAULT_POLICY_ID = "cms-small-cell-v1"

#: The id given to a threshold supplied on the command line. It is deliberately
#: not a well-formed registry id: nothing can pin it from a spec, and a reader
#: of a receipt can tell at a glance that no source backs it.
AD_HOC_POLICY_ID = "ad-hoc"


class UnknownPolicyError(ValueError):
    """Raised when a policy id is not in the registry.

    Fails closed by name. Silently falling back to the default would let a spec
    pin `cms-small-cell-v2`, get `v1`'s behaviour, and record the wrong policy
    id in every receipt it produced.
    """


@dataclass(frozen=True, slots=True)
class SuppressionPolicy:
    """One named suppression rule, and where its number comes from."""

    policy_id: str
    threshold: int
    complementary_rule: bool
    citation: str
    #: The source's URL, kept apart from the prose rather than embedded in it.
    #: A caller that needs the source needs the URL itself, and pulling it back
    #: out of a sentence means a substring test against a URL -- the
    #: `py/incomplete-url-substring-sanitization` shape, which is a real
    #: anti-pattern wherever the result is trusted. Two fields, one exact.
    citation_url: str
    #: The date the citation was last read, not the date the guidance issued.
    #: A citation with no read date cannot be audited for having gone stale.
    citation_read: str

    @property
    def cited(self) -> bool:
        """False for an ad-hoc threshold, which claims no source."""
        return bool(self.citation)


_REGISTRY: dict[str, SuppressionPolicy] = {
    DEFAULT_POLICY_ID: SuppressionPolicy(
        policy_id=DEFAULT_POLICY_ID,
        threshold=11,
        complementary_rule=True,
        citation=(
            "U.S. CMS Cell Size Suppression Policy: counts of 1-10 are suppressed "
            "and derivable cells require complementary suppression."
        ),
        citation_url="https://www.hhs.gov/guidance/document/cms-cell-suppression-policy",
        citation_read="2026-08-21",
    ),
}


def get_policy(policy_id: str) -> SuppressionPolicy:
    """Return the named policy, or fail closed naming the id that was not found."""
    try:
        return _REGISTRY[policy_id]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY))
        raise UnknownPolicyError(
            f"unknown suppression policy {policy_id!r}; registered policies: {known}"
        ) from None


def registered_policies() -> tuple[SuppressionPolicy, ...]:
    """Every registered policy, ordered by id."""
    return tuple(_REGISTRY[key] for key in sorted(_REGISTRY))


def ad_hoc_policy(threshold: int) -> SuppressionPolicy:
    """A policy for an operator-supplied threshold, carrying no citation.

    A threshold below 1 is refused rather than clamped. At threshold 0 or less
    the rule `1 <= |value| < threshold` is empty, so suppression would silently
    become a no-op while still reporting itself as having run -- a privacy
    control that cannot fire, presented as one that did.
    """
    if threshold < 1:
        raise ValueError(f"suppression threshold must be at least 1; got {threshold}")
    return SuppressionPolicy(
        policy_id=AD_HOC_POLICY_ID,
        threshold=threshold,
        complementary_rule=True,
        citation="",
        citation_url="",
        citation_read="",
    )
