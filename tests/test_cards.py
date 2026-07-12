from pathlib import Path

from outcome_receipts.cards import render_data_card, render_model_card, write_cards
from outcome_receipts.cli import EXIT_OK, EXIT_VERIFY_FAIL, main


def test_committed_cards_match_generator() -> None:
    docs = Path(__file__).resolve().parents[1] / "docs"
    assert (docs / "MODEL-CARD.md").read_text() == render_model_card()
    assert (docs / "DATA-CARD.md").read_text() == render_data_card()


def test_card_check_fails_closed_on_drift(tmp_path: Path) -> None:
    assert write_cards(tmp_path)
    assert main(["cards", "--out", str(tmp_path), "--check"]) == EXIT_OK
    (tmp_path / "MODEL-CARD.md").write_text("stale")
    assert main(["cards", "--out", str(tmp_path), "--check"]) == EXIT_VERIFY_FAIL
