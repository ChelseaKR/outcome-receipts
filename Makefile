.PHONY: install verify lint type test eval run clean

# Reproduce the full local toolchain. CI mirrors `make verify` byte for byte.
# --frozen: install exactly what uv.lock records, never re-resolve; a lockfile
# drift becomes a loud CI failure instead of a silently different toolchain.
install:
	uv sync --frozen --python 3.12 --group dev

lint:
	.venv/bin/ruff check src tests
	.venv/bin/ruff format --check src tests

type:
	.venv/bin/python -m mypy

test:
	.venv/bin/python -m pytest

verify: lint type test

# Regenerate the committed eval report. Run after any change to the gate or specs.
eval:
	.venv/bin/receipts eval \
		--config examples/housing-demo/report.toml \
		--out eval/report.md

# Run the demo end to end and write outputs to ./out. The demo approver makes
# the non-interactive export explicit; a real report is signed off by a person.
run:
	.venv/bin/receipts run --config examples/housing-demo/report.toml --out out --approved-by "make run (demo)"

clean:
	rm -rf out .pytest_cache .mypy_cache .ruff_cache
