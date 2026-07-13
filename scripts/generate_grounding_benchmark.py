"""Regenerate the 100-case bilingual grounding benchmark."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "grounding-benchmark.jsonl"


def main() -> None:
    """Write stable EN/ES pass and planted-failure cases."""

    rows: list[dict[str, object]] = []
    for language in ("en", "es"):
        for offset in range(25):
            value = 100 + offset
            served = (
                f"We served {value} people."
                if language == "en"
                else f"Atendimos a {value} personas."
            )
            rows.append(
                {
                    "id": f"{language}-grounded-{offset:02d}",
                    "language": language,
                    "display": str(value),
                    "narrative": served,
                    "should_pass": True,
                }
            )
            invented = (
                f"We served {value} people and invented {900 + offset}."
                if language == "en"
                else f"Atendimos a {value} personas e inventamos {900 + offset}."
            )
            rows.append(
                {
                    "id": f"{language}-injected-{offset:02d}",
                    "language": language,
                    "display": str(value),
                    "narrative": invented,
                    "should_pass": False,
                }
            )
    OUT.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
