.PHONY: install install-security install-smoke verify lint type test hygiene security i18n \
	a11y build-html cards benchmark eval eval-check mutation run clean

# Reproduce the full local toolchain. CI mirrors `make verify` byte for byte.
# --frozen: install exactly what uv.lock records, never re-resolve; a lockfile
# drift becomes a loud CI failure instead of a silently different toolchain.
install: install-security
	uv sync --frozen --python 3.12 --group dev
	npm ci
	npx playwright install chromium

install-security:
	./scripts/install-security-tools.sh

# On a fresh checkout this proves the documented one-command install path
# provisioned every executable later consumed by `make verify`.
install-smoke: install
	test -x .venv/bin/receipts
	test -x .tools/osv-scanner
	test -x .tools/gitleaks
	node -e "const fs=require('node:fs'); const {chromium}=require('playwright'); fs.accessSync(chromium.executablePath(), fs.constants.X_OK)"

lint:
	.venv/bin/ruff check src tests
	.venv/bin/ruff format --check src tests

type:
	.venv/bin/python -m mypy

test:
	.venv/bin/python -m pytest
	.venv/bin/coverage report \
		--include="src/outcome_receipts/grounding.py,src/outcome_receipts/engine.py,src/outcome_receipts/suppression.py,src/outcome_receipts/bundle.py,src/outcome_receipts/verify.py" \
		--fail-under=95

hygiene:
	.venv/bin/python scripts/check_source_hygiene.py
	.venv/bin/python scripts/check_conformance.py

# Keep ephemeral Python tools on the same interpreter as the locked project. In
# particular, Semgrep's macOS source distribution does not carry semgrep-core.
security:
	.venv/bin/pip-audit --local
	npm audit --audit-level=high
	.tools/osv-scanner --lockfile uv.lock
	.tools/gitleaks detect --source . --redact --exit-code 1
	uvx --python 3.12 --from semgrep==1.168.0 semgrep scan \
		--config p/default --config p/python --severity ERROR --error --metrics off
	uvx --python 3.12 --from zizmor==1.16.3 zizmor .github/workflows/

i18n:
	.venv/bin/pybabel extract -F babel.cfg --no-location --omit-header \
		-o /tmp/outcome-receipts-messages.pot src
	cmp /tmp/outcome-receipts-messages.pot src/outcome_receipts/locales/messages.pot
	.venv/bin/pybabel compile -d src/outcome_receipts/locales --statistics
	git diff --exit-code -- src/outcome_receipts/locales
	.venv/bin/python scripts/check_i18n.py

build-html:
	rm -rf out/a11y
	.venv/bin/receipts run --config examples/housing-demo/report.toml \
		--out out/a11y --ledger out/a11y/export-ledger.jsonl \
		--approved-by "Automated accessibility gate" --reproducible

a11y: build-html
	npm run a11y

cards:
	.venv/bin/receipts cards --out docs/cards --check

benchmark:
	.venv/bin/python scripts/generate_grounding_benchmark.py

eval-check: benchmark eval
	git diff --exit-code -- eval/report.md eval/grounding-benchmark.jsonl

verify: lint type test hygiene i18n security a11y cards eval-check

# Mutation testing over the invariant core (grounding gate + engine). Slow, so it
# is opt-in and not part of `verify`. A low surviving-mutant count is evidence the
# gate tests — including the Hypothesis property tests — actually pin the behavior.
mutation:
	.venv/bin/mutmut run

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
	rm -rf out .pytest_cache .mypy_cache .ruff_cache .lighthouseci
