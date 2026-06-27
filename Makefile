.PHONY: install verify lint type test eval run clean

# Reproduce the full local toolchain. CI mirrors `make verify` byte for byte.
install:
	uv venv --python 3.11 .venv
	uv pip install --python .venv/bin/python -e ".[dev]"

lint:
	.venv/bin/ruff check src tests

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

# Run the demo end to end and write outputs to ./out.
run:
	.venv/bin/receipts run --config examples/housing-demo/report.toml --out out

clean:
	rm -rf out .pytest_cache .mypy_cache .ruff_cache
