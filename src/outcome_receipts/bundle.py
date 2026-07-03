"""A tamper-evident, self-contained signature over a set of export files.

``receipts run`` writes a report, a receipts manifest, a trace view, and any
charts. An auditor who receives those files wants one more thing: assurance that
what they hold is what was exported, byte for byte, and that no member was quietly
swapped after the fact. ``bundle.py`` provides it without a signing service.

The bundle manifest lists every member file with a BLAKE2b-256 hash of its bytes,
sorted by name, plus a ``bundle_digest`` that is a BLAKE2b hash over the
canonicalized ``(name, digest)`` list. That digest alone is tamper-evident: change
any byte of any member, or add or drop a file, and re-hashing no longer matches.
When a key is supplied, a keyed BLAKE2b ``signature`` over the same canonical bytes
is added, so a holder of the key can prove the bundle was sealed by someone who
had it, with no external service, network, or OIDC in the loop.

Verification fails closed, exactly like ``receipts verify``: every mismatched,
missing, or extra member is reported, and a single failure makes the whole bundle
fail. The canonicalization mirrors ``engine._slice_hash`` so re-bundling the same
files reproduces the same digests, and this reuses the portfolio hash-chain pattern
rather than introducing a new dependency.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# BLAKE2b-256, matching the slice-hash digest size used across the engine.
_DIGEST_SIZE = 32


@dataclass(frozen=True)
class BundleCheck:
    """The verification outcome for one member (or aggregate) of a bundle."""

    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class BundleVerifyResult:
    """Every per-member check, plus whether the bundle verified as a whole."""

    checks: tuple[BundleCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def n_ok(self) -> int:
        return sum(1 for check in self.checks if check.ok)


def _digest(content: bytes) -> str:
    """BLAKE2b-256 of a member's raw bytes, as hex."""

    return hashlib.blake2b(content, digest_size=_DIGEST_SIZE).hexdigest()


def _canonical(files: Mapping[str, bytes]) -> bytes:
    """Canonical bytes over the sorted ``(name, digest)`` list of the members.

    Sorting by name and compact, non-ASCII-escaping JSON makes the bytes depend
    only on the member set and their contents, never on iteration order, so
    re-bundling identical files reproduces an identical digest and signature.
    """

    pairs = [[name, _digest(files[name])] for name in sorted(files)]
    return json.dumps(pairs, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _signature(canonical: bytes, key: bytes) -> str:
    """Keyed BLAKE2b over the canonical bytes, as hex."""

    return hashlib.blake2b(canonical, key=key, digest_size=_DIGEST_SIZE).hexdigest()


def bundle_manifest(files: Mapping[str, bytes], *, key: bytes | None = None) -> str:
    """Build the JSON bundle manifest for a set of export files.

    The manifest lists each member's name and BLAKE2b-256 content digest, sorted by
    name, and a ``bundle_digest`` over the canonicalized ``(name, digest)`` list.
    When ``key`` is given, a keyed-BLAKE2b ``signature`` over the same canonical
    bytes is added: a self-contained, tamper-evident seal that needs no external
    service. The default (no key) is still tamper-evident by the digests alone.
    """

    canonical = _canonical(files)
    payload: dict[str, Any] = {
        "members": [
            {"name": name, "digest": _digest(files[name])} for name in sorted(files)
        ],
        "bundle_digest": hashlib.blake2b(canonical, digest_size=_DIGEST_SIZE).hexdigest(),
    }
    if key is not None:
        payload["signature"] = _signature(canonical, key)
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def verify_bundle(
    files: Mapping[str, bytes],
    manifest: Mapping[str, Any],
    *,
    key: bytes | None = None,
) -> BundleVerifyResult:
    """Check that the files match the bundle manifest, failing closed on any drift.

    Each member's digest is recomputed from the bytes on hand and compared to the
    manifest; a member the manifest names but the files omit is missing, and a file
    with no manifest member is extra. The ``bundle_digest`` is recomputed and
    compared, and, when ``key`` is given, the keyed signature. Every mismatch is
    reported and any one of them makes the result not ``ok``.
    """

    checks: list[BundleCheck] = []
    stored_members = {
        str(member.get("name", "")): str(member.get("digest", ""))
        for member in manifest.get("members", [])
    }

    for name in sorted(set(files) | set(stored_members)):
        if name not in stored_members:
            checks.append(BundleCheck(name, False, "TAMPERED: file not in manifest"))
        elif name not in files:
            checks.append(BundleCheck(name, False, "TAMPERED: manifest member missing"))
        else:
            want = stored_members[name]
            got = _digest(files[name])
            if got == want:
                checks.append(BundleCheck(name, True, "content digest matches"))
            else:
                checks.append(
                    BundleCheck(
                        name, False, f"TAMPERED: digest {got} != manifest {want}"
                    )
                )

    canonical = _canonical(files)
    stored_digest = str(manifest.get("bundle_digest", ""))
    recomputed_digest = hashlib.blake2b(canonical, digest_size=_DIGEST_SIZE).hexdigest()
    if hmac.compare_digest(recomputed_digest, stored_digest):
        checks.append(BundleCheck("bundle_digest", True, "bundle digest matches"))
    else:
        checks.append(
            BundleCheck("bundle_digest", False, "TAMPERED: bundle digest does not match")
        )

    if key is not None:
        stored_signature = str(manifest.get("signature", ""))
        recomputed_signature = _signature(canonical, key)
        if stored_signature and hmac.compare_digest(recomputed_signature, stored_signature):
            checks.append(BundleCheck("signature", True, "keyed signature matches"))
        else:
            checks.append(
                BundleCheck("signature", False, "TAMPERED: keyed signature does not match")
            )

    return BundleVerifyResult(tuple(checks))
