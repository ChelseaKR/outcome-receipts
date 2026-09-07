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


def _assert_mutated(original: str, mutated: str) -> None:
    """A negative control that did not change anything proves nothing.

    Every regression test below builds its input by mutating the shipped file,
    which keeps the fixture from drifting away from what is actually deployed
    but makes each one a string match against text the workflow is free to
    reformat. When a match stops applying, `str.replace` returns the original
    silently and the test that follows reports the *checker* as broken. This
    turns that into the true message, at the point where it is still true.
    """

    assert mutated != original, (
        "the mutation did not apply: its anchor no longer matches "
        f"{WORKFLOW.relative_to(ROOT)}, so this negative control proved nothing"
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


def _needs(job_text: str) -> list[str]:
    """The job names one job's `needs:` declares, in either YAML form."""

    match = re.search(r"^    needs:[ \t]*(.+)$", job_text, re.MULTILINE)
    if match is None:
        return []
    value = match.group(1).split("#", 1)[0].strip()
    if value.startswith("["):
        value = value.strip("[]")
    return [name.strip() for name in value.split(",") if name.strip()]


def _needs_closure(jobs: dict[str, str], start: str) -> set[str]:
    """Every job `start` transitively depends on."""

    seen: set[str] = set()
    pending = list(_needs(jobs[start]))
    while pending:
        name = pending.pop()
        if name in seen or name not in jobs:
            continue
        seen.add(name)
        pending.extend(_needs(jobs[name]))
    return seen


def _verify_checks_the_tag_against_the_manifest(job_text: str) -> bool:
    """Does the `verify` job compare the release tag with `project.version`?

    `uv build` in the `build` job stamps the wheel with `project.version` from
    `pyproject.toml`, and nothing in this workflow used to compare that with
    the tag being published. The existing CHANGELOG step is not the same check:
    it greps for a section heading, which a tree with a stale
    `pyproject.toml` satisfies -- and `main` was in exactly that state on
    2026-09-07 (CHANGELOG `0.2.1`, manifest `0.2.0`) with every gate green.
    """

    return "check_release_version.py --tag" in job_text and '"$RELEASE_TAG"' in job_text


# ---------------------------------------------------------------------------
# Trigger: dispatch-only, no tag-push path.
# ---------------------------------------------------------------------------


def test_dispatch_only_no_push_trigger() -> None:
    trigger = _trigger_block(_text())
    assert "workflow_dispatch:" in trigger
    assert "push:" not in trigger


def test_reintroduced_tag_push_trigger_is_caught() -> None:
    original = _text()
    mutated = original.replace(
        "on:\n  workflow_dispatch:",
        "on:\n  push:\n    tags: ['v*']\n  workflow_dispatch:",
    )
    _assert_mutated(original, mutated)

    trigger = _trigger_block(mutated)
    assert "push:" in trigger  # exactly the regression the real-file test forbids


# ---------------------------------------------------------------------------
# Default token stays least-privilege; elevation is per-job only.
# ---------------------------------------------------------------------------


def test_default_token_permission_is_contents_read_only() -> None:
    assert _default_permissions(_text()) == ["contents: read"]


def test_widened_default_token_permission_is_caught() -> None:
    original = _text()
    mutated = original.replace(
        "permissions:\n  contents: read\n", "permissions:\n  contents: write\n"
    )
    _assert_mutated(original, mutated)

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
    original = _jobs(_text())["authorize"]
    mutated = original.replace("@315a513ff3b4e7c5c0628428909052d947f4f1ab", "@main")
    _assert_mutated(original, mutated)

    match = REUSABLE_AUTHORIZE_RE.search(mutated)
    assert match is not None
    assert not re.fullmatch(r"[0-9a-f]{40}", match.group(1))  # "main" is not a 40-hex-char pin


# ---------------------------------------------------------------------------
# Split authority: exactly one write-capable job, and it never checks out code.
# ---------------------------------------------------------------------------


def test_exactly_one_job_holds_contents_write_and_it_is_github_release() -> None:
    assert _write_jobs(_text()) == ["github-release"]


def test_widening_write_scope_onto_another_job_is_caught() -> None:
    original = _text()
    # Anchored on the job's `name:` line alone. The previous anchor spanned
    # `needs:`, `runs-on:` and `steps:` as one literal block, so adding
    # `timeout-minutes:` between them turned the mutation into a no-op and this
    # test failed as "['github-release'] != ['github-release', 'verify']" --
    # which reads like the checker regressed when in fact the sabotage never
    # applied. _assert_mutated below is the general fix; this is the narrow one.
    mutated = original.replace(
        "    name: verify at tagged commit\n",
        "    name: verify at tagged commit\n    permissions:\n      contents: write\n",
    )
    _assert_mutated(original, mutated)

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
    _assert_mutated(original, mutated)

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
    _assert_mutated(job, mutated)

    assert not _pypi_publish_rechecks_tag_before_publishing(mutated)


# ---------------------------------------------------------------------------
# The version the wheel will carry is compared with the tag, before the build.
# ---------------------------------------------------------------------------


def test_verify_compares_the_tag_with_the_version_the_wheel_will_carry() -> None:
    assert _verify_checks_the_tag_against_the_manifest(_jobs(_text())["verify"])


def test_removing_the_tagged_version_check_is_caught() -> None:
    job = _jobs(_text())["verify"]
    step_start = job.index("- name: The version the wheel will carry is the version being tagged")
    mutated = job[:step_start].rstrip() + "\n"
    _assert_mutated(job, mutated)

    assert not _verify_checks_the_tag_against_the_manifest(mutated)


def test_the_check_runs_in_verify_which_gates_every_job_that_publishes() -> None:
    """Placement is the whole point: it must precede anything irreversible.

    Every publishing job must reach `verify` through its `needs:` closure, so a
    mismatch stops the run before `uv build` produces a wheel, before Sigstore
    attests it, and above all before `pypi-publish` uploads it -- a PyPI
    filename cannot be re-used, so `verify-published` catching a mismatch
    afterwards is not a repair, only a report.

    The closure is walked rather than substring-matched: the word "verify"
    appears in several of these job bodies for unrelated reasons, and a test
    that accepted any of them would pass on a workflow where the dependency had
    actually been cut.
    """

    jobs = _jobs(_text())
    assert _verify_checks_the_tag_against_the_manifest(jobs["verify"])
    for downstream in ("build", "github-release", "pypi-publish"):
        assert "verify" in _needs_closure(jobs, downstream), (
            f"{downstream} no longer reaches the verify gate through its needs closure"
        )


def test_the_tag_is_passed_through_the_environment_not_interpolated() -> None:
    """A tag name is attacker-influenced for anyone who can push a tag.

    `${{ }}` interpolation directly into a `run:` body is a template-injection
    vector, which is why this workflow routes the tag through `env:` as
    `RELEASE_TAG`. The new step must not be the one place that regresses it.
    """

    job = _jobs(_text())["verify"]
    step_start = job.index("- name: The version the wheel will carry is the version being tagged")
    step = job[step_start:]
    assert "${{" not in step.split("- name:")[1]


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
