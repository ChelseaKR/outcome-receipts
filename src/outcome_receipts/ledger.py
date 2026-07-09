"""A tamper-evident, hash-chained export ledger.

Every successful export writes one line to an append-only JSONL ledger: what
report was exported, to whom, when, and a hash of the receipts manifest that
shipped. Each entry carries the ``entry_hash`` of the entry before it, so the
entries form a chain. Recomputing an entry's hash and checking it against the
``prev_hash`` of the next entry detects any edit, insertion, deletion, or
reordering after the fact. The record of what was reported to whom is itself
receipted.

The hash construction mirrors the receipt slice hash in ``engine.py``:
``blake2b`` with a 32-byte digest over a canonical JSON payload, so the same
inputs always yield the same hash and the ledger is byte-for-byte reproducible
under a fixed clock. The timestamp comes from the injected ``Clock`` for the
same reason the receipts do.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path

from outcome_receipts.clock import Clock, SystemClock

# The prev_hash of the genesis entry: there is no prior entry to link to, so the
# chain is anchored to a fixed all-zero hash. This matches EMPTY_SLICE_HASH's
# "0" * 64 convention in models.py for a stand-in hash.
GENESIS_PREV_HASH = "0" * 64

# The entry fields that make up the hashed payload: every field except the hash
# itself. Held as a tuple so canonical_payload and the JSON line agree on the
# schema and a new field cannot be hashed in one place and forgotten in another.
_PAYLOAD_FIELDS = (
    "index",
    "timestamp",
    "report_title",
    "manifest_hash",
    "recipient",
    "prev_hash",
)


@dataclass(frozen=True)
class LedgerEntry:
    """One append-only record of a successful export.

    ``index`` is the 0-based position in the chain. ``manifest_hash`` is a
    BLAKE2b hash of the receipts manifest that shipped, so the exported numbers
    are pinned by the entry. ``recipient`` is who the report went to, or ``None``
    when it was not recorded. ``prev_hash`` is the ``entry_hash`` of the previous
    entry (or ``GENESIS_PREV_HASH`` for the first), and ``entry_hash`` is the
    BLAKE2b hash over every other field, which is what the next entry links to.
    """

    index: int
    timestamp: str
    report_title: str
    manifest_hash: str
    recipient: str | None
    prev_hash: str
    entry_hash: str


def canonical_payload(entry: LedgerEntry) -> str:
    """Deterministic JSON of every field except ``entry_hash``.

    Keys are sorted and whitespace is fixed, so the same entry always serializes
    to the same string and therefore the same hash. ``entry_hash`` is excluded
    because it is the output of hashing this payload.
    """

    payload = {name: getattr(entry, name) for name in _PAYLOAD_FIELDS}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_entry_hash(payload: str) -> str:
    """BLAKE2b-256 hex digest of a canonical payload, matching the engine style."""

    return hashlib.blake2b(payload.encode("utf-8"), digest_size=32).hexdigest()


def _manifest_hash(manifest_json_or_hash: str) -> str:
    """Hash of the receipts manifest, or a pre-computed hash passed straight through.

    The caller normally passes the receipts.json text, which is hashed as bytes.
    A caller that already holds the 64-hex-character digest can pass it instead,
    so the ledger does not force a re-read of a manifest that is already hashed.
    """

    candidate = manifest_json_or_hash.strip()
    if len(candidate) == 64 and all(c in "0123456789abcdef" for c in candidate):
        return candidate
    return hashlib.blake2b(manifest_json_or_hash.encode("utf-8"), digest_size=32).hexdigest()


def read_ledger(ledger_path: Path) -> list[LedgerEntry]:
    """Read the JSONL ledger into entries, or return an empty list if absent.

    Blank lines are skipped so a trailing newline does not read as a broken
    entry. Each line is one JSON object with exactly the ``LedgerEntry`` fields.
    """

    if not ledger_path.exists():
        return []
    entries: list[LedgerEntry] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        entries.append(
            LedgerEntry(
                index=int(record["index"]),
                timestamp=str(record["timestamp"]),
                report_title=str(record["report_title"]),
                manifest_hash=str(record["manifest_hash"]),
                recipient=(None if record["recipient"] is None else str(record["recipient"])),
                prev_hash=str(record["prev_hash"]),
                entry_hash=str(record["entry_hash"]),
            )
        )
    return entries


def append_export(
    ledger_path: Path,
    report_title: str,
    manifest_json_or_hash: str,
    recipient: str | None,
    clock: Clock | None = None,
) -> LedgerEntry:
    """Append one export to the hash-chained ledger and return the new entry.

    The prior entry's ``entry_hash`` becomes this entry's ``prev_hash`` (the
    genesis entry links to ``GENESIS_PREV_HASH``). ``manifest_hash`` is the
    BLAKE2b hash of the receipts manifest. The entry's own hash is computed over
    its canonical payload and the entry is written as one JSON line. The
    timestamp comes from the injected clock so a ``--reproducible`` run is
    byte-for-byte stable.
    """

    clock = clock or SystemClock()
    entries = read_ledger(ledger_path)
    prev_hash = entries[-1].entry_hash if entries else GENESIS_PREV_HASH

    draft = LedgerEntry(
        index=len(entries),
        timestamp=clock.now_iso(),
        report_title=report_title,
        manifest_hash=_manifest_hash(manifest_json_or_hash),
        recipient=recipient,
        prev_hash=prev_hash,
        entry_hash="",
    )
    entry = replace(draft, entry_hash=compute_entry_hash(canonical_payload(draft)))

    line = json.dumps(
        {
            "index": entry.index,
            "timestamp": entry.timestamp,
            "report_title": entry.report_title,
            "manifest_hash": entry.manifest_hash,
            "recipient": entry.recipient,
            "prev_hash": entry.prev_hash,
            "entry_hash": entry.entry_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return entry


def verify_chain(ledger_path: Path) -> list[str]:
    """Check the ledger's integrity and return a list of problems, empty if intact.

    For each entry: the recomputed ``entry_hash`` must match the stored one (no
    field was edited), the ``prev_hash`` must equal the previous entry's
    ``entry_hash`` (the link holds), and the ``index`` must be contiguous from
    zero (nothing was inserted, dropped, or reordered). Each problem names the
    index where the break was found, so a tampered middle entry is located.
    """

    entries = read_ledger(ledger_path)
    problems: list[str] = []
    for position, entry in enumerate(entries):
        if entry.index != position:
            problems.append(
                f"entry {position}: index {entry.index} is not contiguous (expected {position})"
            )
        expected_prev = GENESIS_PREV_HASH if position == 0 else entries[position - 1].entry_hash
        if entry.prev_hash != expected_prev:
            problems.append(f"entry {entry.index}: prev_hash does not link to the previous entry")
        recomputed = compute_entry_hash(canonical_payload(entry))
        if recomputed != entry.entry_hash:
            problems.append(f"entry {entry.index}: entry_hash mismatch, the record was altered")
    return problems
