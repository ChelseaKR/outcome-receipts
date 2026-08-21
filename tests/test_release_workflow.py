"""Shape tests for the release workflow's split-authority trust boundary.

`.github/workflows/release.yml` is the only place in this repository with a
`contents: write` job, the workflow that publishes to PyPI, and the workflow
that signs Sigstore attestations. Nothing asserted its shape until now:
`git grep -l "release.yml\\|release_workflow" -- tests/ scripts/` returned
nothing on main as of 2026-08-15 (issue 95).

Draft PR 66 ("Harden Outcome Receipts release trust boundary", opened
2026-07-24) once carried a `tests/test_release_workflow.py` pinning four
properties of a two-job `verify-build` / `publish-release` design. That
design was superseded on main by a different and better route -- 94b8054
(#83), 787dd05 (#84), 5fa3723 (#85) -- which delegates tag/signature
authorization to the standards-owned reusable `release-authorize` workflow
and splits publication into `authorize` / `verify` / `build` /
`github-release` / `pypi-publish` / `verify-published`. PR 66's tests
reference job names (`verify-build`, `publish-release`) that no longer exist
on main, so they could not be cherry-picked. This file is a rebuild against
the job layout actually on main, so the next restructuring cannot drop the
coverage silently the way the first one did. PR 66 is closed as superseded;
its salvageable parts (the `.github/allowed_signers` fingerprint header and
`docs/RELEASING.md`) land alongside this file.

What is, and is not, checked here: the actual SSH-signature verification
against `.github/allowed_signers` happens inside the pinned reusable
`release-authorize.yml` workflow, which lives in a different repository
(`ChelseaKR/.github`) and is out of this repo's test reach -- that workflow's
own repository owns testing its internals. What *is* checked from here: that
`.github/allowed_signers` exists and is non-empty, that `authorize` delegates
to the reusable workflow pinned by a full 40-character commit SHA rather than
a movable tag or branch (the property that makes the delegation itself
tamper-evident), and that release.yml's own comments name the file as the
control the delegated job enforces.

Every property below is proven two ways, in the spirit of
`tests/test_npm_audit_gate.py`: the real file satisfies it, and a
deliberately regressed copy of the same text -- built by mutating the real
file's text, so the mutation is anchored to what is actually shipped rather
than to a hand-written fixture that could drift from it -- fails it. Each
mutation is one of the four regressions issue 95 names as currently able to
pass every existing gate:

  * reintroducing a `push: tags:` trigger
  * widening `permissions:` on a job other than `github-release`, or adding
    a checkout to `github-release`
  * dropping the tag recheck in `pypi-publish`
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
ALLOWED_SIGNERS = ROOT / ".github" / "allowed_signers"

REUSABLE_AUTHORIZE_RE = re.compile(
    r"uses:\s*ChelseaKR/\.github/\.github/workflows/release-authorize\.yml@(\S+)"
)


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _trigger_block(text: str) -> str:
    """The literal body of the top-level `on:` key."""

    match = re.search(r"^on:\n(.*?)^\S", text, re.MULTILINE | re.DOTALL)
    assert match is not None, "workflow has no `on:` block"
    return match.group(1)


def _default_permissions(text: str) -> list[str]:
    """The literal lines of the top-level (workflow-default) `permissions:` key."""

    match = re.search(r"^permissions:\n((?:  \S.*\n?)+)", text, re.MULTILINE)
    assert match is not None, "workflow has no top-level `permissions:` block"
    return [line.strip() for line in match.group(1).splitlines() if line.strip()]


def _jobs(text: str) -> dict[str, str]:
    """job name -> raw block text, split on the 2-space-indented job keys under `jobs:`."""

    marker = "\njobs:\n"
    start = text.index(marker)
    body = text[start + len(marker) :]
    parts = re.split(r"(?=^  [A-Za-z][\w-]*:[ \t]*\n)", body, flags=re.MULTILINE)
    out: dict[str, str] = {}
    for part in parts:
        head = re.match(r"^  ([A-Za-z][\w-]*):", part)
        if head:
            out[head.group(1)] = part
    return out


def _job_permissions(job_text: str) -> dict[str, str]:
    """job-level `permissions:` sub-block as a {scope: value} mapping (empty if absent)."""

    match = re.search(r"^    permissions:\n((?:      \S.*\n?)+)", job_text, re.MULTILINE)
    if not match:
        return {}
    perms: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, _, value = line.strip().partition(":")
        perms[key.strip()] = value.split("#", 1)[0].strip()
    return perms


def _write_jobs(text: str) -> list[str]:
    """Every job name whose own `permissions:` block grants `contents: write`."""

    return [
        name
        for name, block in _jobs(text).items()
        if _job_permissions(block).get("contents") == "write"
    ]


def _uses_checkout(job_text: str) -> bool:
    return "actions/checkout@" in job_text


def _pypi_publish_rechecks_tag_before_publishing(job_text: str) -> bool:
    recheck = job_text.find("TAG_OBJECT_SHA")
    publish = job_text.find("Publish to PyPI")
    return recheck != -1 and publish != -1 and recheck < publish


# ---------------------------------------------------------------------------
# Trigger: dispatch-only, no tag-push path.
# ---------------------------------------------------------------------------


def test_dispatch_only_no_push_trigger() -> None:
    trigger = _trigger_block(_text())
    assert "workflow_dispatch:" in trigger
    assert "push:" not in trigger


def test_reintroduced_tag_push_trigger_is_caught() -> None:
    mutated = _text().replace(
        "on:\n  workflow_dispatch:",
        "on:\n  push:\n    tags: ['v*']\n  workflow_dispatch:",
    )
    trigger = _trigger_block(mutated)
    assert "push:" in trigger  # exactly the regression the real-file test forbids


# ---------------------------------------------------------------------------
# Default token stays least-privilege; elevation is per-job only.
# ---------------------------------------------------------------------------


def test_default_token_permission_is_contents_read_only() -> None:
    assert _default_permissions(_text()) == ["contents: read"]


def test_widened_default_token_permission_is_caught() -> None:
    mutated = _text().replace(
        "permissions:\n  contents: read\n", "permissions:\n  contents: write\n"
    )
    assert _default_permissions(mutated) != ["contents: read"]


# ---------------------------------------------------------------------------
# Authorization is delegated to the pinned, standards-owned reusable workflow.
# ---------------------------------------------------------------------------


def test_authorize_delegates_to_the_pinned_reusable_workflow_by_full_sha() -> None:
    match = REUSABLE_AUTHORIZE_RE.search(_jobs(_text())["authorize"])
    assert match is not None
    pin = match.group(1)
    assert re.fullmatch(r"[0-9a-f]{40}", pin), f"authorize must pin a full commit SHA, got {pin!r}"


def test_a_movable_ref_pin_on_authorize_is_caught() -> None:
    mutated = _jobs(_text())["authorize"].replace(
        "@315a513ff3b4e7c5c0628428909052d947f4f1ab", "@main"
    )
    match = REUSABLE_AUTHORIZE_RE.search(mutated)
    assert match is not None
    assert not re.fullmatch(r"[0-9a-f]{40}", match.group(1))  # "main" is not a 40-hex-char pin


# ---------------------------------------------------------------------------
# Split authority: exactly one write-capable job, and it never checks out code.
# ---------------------------------------------------------------------------


def test_exactly_one_job_holds_contents_write_and_it_is_github_release() -> None:
    assert _write_jobs(_text()) == ["github-release"]


def test_widening_write_scope_onto_another_job_is_caught() -> None:
    mutated = _text().replace(
        "  verify:\n    name: verify at tagged commit\n"
        "    needs: authorize\n    runs-on: ubuntu-latest\n    steps:",
        "  verify:\n    name: verify at tagged commit\n"
        "    needs: authorize\n    runs-on: ubuntu-latest\n"
        "    permissions:\n      contents: write\n    steps:",
    )
    assert sorted(_write_jobs(mutated)) == ["github-release", "verify"]


def test_github_release_performs_no_checkout() -> None:
    assert not _uses_checkout(_jobs(_text())["github-release"])


def test_a_checkout_added_to_github_release_is_caught() -> None:
    original = _jobs(_text())["github-release"]
    mutated = original.replace(
        "    steps:\n      - name: Download the attested release assets",
        "    steps:\n      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5\n"
        "      - name: Download the attested release assets",
    )
    assert _uses_checkout(mutated)


# ---------------------------------------------------------------------------
# The published bytes are re-proven to match the authorized tag before PyPI.
# ---------------------------------------------------------------------------


def test_pypi_publish_rechecks_the_tag_object_before_publishing() -> None:
    assert _pypi_publish_rechecks_tag_before_publishing(_jobs(_text())["pypi-publish"])


def test_removing_the_pypi_tag_recheck_is_caught() -> None:
    job = _jobs(_text())["pypi-publish"]
    step_start = job.index("- name: Recheck the immutable tag object before PyPI publication")
    step_end = job.index("- name: Publish to PyPI")
    mutated = job[:step_start] + job[step_end:]
    assert not _pypi_publish_rechecks_tag_before_publishing(mutated)


# ---------------------------------------------------------------------------
# The signer registry the delegated authorization step verifies against.
# ---------------------------------------------------------------------------


def test_allowed_signers_exists_is_nonempty_and_is_named_by_the_workflow() -> None:
    assert ALLOWED_SIGNERS.exists()
    content = ALLOWED_SIGNERS.read_text(encoding="utf-8").strip()
    assert content
    assert "ssh-ed25519" in content
    assert ".github/allowed_signers" in _text()


def test_allowed_signers_holds_a_public_key_only() -> None:
    content = ALLOWED_SIGNERS.read_text(encoding="utf-8")
    for private_marker in ("PRIVATE KEY", "BEGIN OPENSSH PRIVATE"):
        assert private_marker not in content
