"""Pin the release workflow's split-authority security contract."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
ALLOWED_SIGNERS = ROOT / ".github" / "allowed_signers"


def _job(text: str, name: str, next_name: str | None) -> str:
    start = text.index(f"  {name}:")
    end = text.index(f"  {next_name}:", start) if next_name else len(text)
    return text[start:end]


def test_release_starts_from_trusted_main_and_a_signed_reviewed_tag() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    verify = _job(text, "verify-build", "publish-release")

    assert "workflow_dispatch:" in text
    assert "push:\n    tags:" not in text
    assert "contents: read" in verify
    assert "actions/checkout@" in verify
    assert "ref: main" in verify
    assert '"${GITHUB_REF}" = refs/heads/main' in verify
    assert "git cat-file -t" in verify
    assert "git verify-tag" in verify
    assert "gpg.ssh.allowedSignersFile" in verify
    assert "git merge-base --is-ancestor" in verify
    assert "make verify" in verify
    assert "actions/upload-artifact@" in verify


def test_write_capable_publisher_is_checkout_free_and_rechecks_tag_object() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    publish = _job(text, "publish-release", "pypi-publish")

    assert "contents: write" in publish
    assert "actions/download-artifact@" in publish
    assert "actions/checkout@" not in publish
    assert "git/ref/tags/${TAG}" in publish
    assert "--jq .object.sha" in publish
    assert "TAG_OBJECT_SHA" in publish
    assert "gh release create" in publish
    assert "gh release upload" in publish


def test_pypi_publisher_receives_verified_bytes_and_cannot_rebuild() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    pypi = _job(text, "pypi-publish", "verify-published")

    assert "needs: [verify-build, publish-release]" in pypi
    assert "actions/download-artifact@" in pypi
    assert "sha256sum -c SHA256SUMS" in pypi
    assert "pypa/gh-action-pypi-publish@" in pypi
    assert "actions/checkout@" not in pypi
    assert "uv build" not in pypi


def test_allowed_signers_contains_only_the_public_release_identity() -> None:
    text = ALLOWED_SIGNERS.read_text(encoding="utf-8")

    assert "3114598+ChelseaKR@users.noreply.github.com ssh-ed25519 " in text
    assert "PRIVATE KEY" not in text
