"""Static contract tests for the optional self-hosting container.

CI performs the real build, locked-down smoke test, and Trivy scan. These fast
tests keep the security properties visible in the ordinary Python suite, where a
change cannot quietly turn a digest back into a mutable tag or restore root.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
MAKEFILE = ROOT / "Makefile"


def test_container_uses_immutable_base_images_and_frozen_install() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    from_lines = [line for line in text.splitlines() if line.startswith("FROM ")]
    assert len(from_lines) == 3
    assert all("@sha256:" in line for line in from_lines)
    assert "uv sync --frozen --no-dev --no-editable" in text


def test_container_runs_as_an_unprivileged_cli() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "USER 65532:65532" in text
    assert 'ENTRYPOINT ["receipts"]' in text


def test_ci_builds_smokes_and_scans_the_container() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "container (build · smoke · trivy)" in text
    assert "run: make container-verify" in text


def test_make_verify_uses_the_digest_pinned_container_scan() -> None:
    text = MAKEFILE.read_text(encoding="utf-8")
    assert (
        "verify: lint type test hygiene i18n security a11y cards eval-check compat container-verify"
        in text
    )
    assert "aquasec/trivy:0.72.0@sha256:" in text
    assert "--severity HIGH,CRITICAL --exit-code 1" in text
    assert "--input /scan/image.tar" in text
    assert "/var/run/docker.sock" not in text
    assert "--network none --cap-drop ALL" in text
