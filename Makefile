.PHONY: install install-security install-smoke verify lint type test hygiene security i18n compat \
	security-pip security-npm security-osv security-secrets security-semgrep security-workflows \
	a11y build-html cards benchmark eval eval-check mutation run container-build \
	container-smoke container-scan container-verify container-demo clean

# The gate sets, in reporting order. Lists rather than prerequisites, because
# make stops a prerequisite list at the first failure and these gates are
# independent of one another. `verify` aborted at `security` for weeks, so
# `cards`, `eval-check` and `compat` had not run on any commit -- silently,
# because a red job looks the same whether it ran six gates or eleven.
# scripts/run_gates.sh runs every gate, reports each one's own result, and
# exits non-zero if any of them failed. Nothing is muted; nothing is skipped.
SECURITY_GATES := security-pip security-npm security-osv security-secrets \
	security-semgrep security-workflows
VERIFY_GATES := lint type test hygiene i18n security a11y cards eval-check compat \
	container-verify

# Reproduce the full local toolchain. CI mirrors `make verify` byte for byte.
# `uv lock --check` first, because `uv sync --frozen` cannot fail on drift. The
# comment that used to sit here claimed --frozen made "a lockfile drift a loud
# CI failure"; it does not. --frozen means "install exactly what uv.lock
# records and never re-resolve", and it never compares the lock against
# pyproject.toml. Bump `project.version` and leave uv.lock behind and
# `uv sync --frozen` still exits 0, having installed the previous version --
# which is exactly the drift a release creates, so the one change guaranteed to
# desynchronise the lock was the one change this step could not see. Every
# release since would have verified against a stale editable install. `uv lock
# --check` re-resolves and exits 1 when the lock no longer matches the
# manifest; npm's half of the pair (`npm ci`, not `npm install`) already fails
# closed the same way.
install: install-security
	uv lock --check
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
	docker version --format '{{.Server.Version}}'
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
#
# Each scanner is its own target. They used to be six lines of one recipe, and
# make stops a recipe at the first failing line: an unfixable HIGH advisory in
# the npm accessibility toolchain meant `npm audit` failed on line 2 and
# OSV-Scanner, gitleaks, Semgrep and zizmor never ran at all -- while the CI
# job called "security (pip-audit - osv-scanner - gitleaks - zizmor)" reported
# red, which is exactly what it would have reported if they had.
security-pip:
	.venv/bin/pip-audit --local

# npm cannot accept one reviewed advisory: `--audit-level` is its only lever
# and raising it hides every finding at that severity. The floor stays at HIGH
# and scripts/check_npm_audit.py adjudicates against waivers.yml instead, so
# anything without a live, exact waiver still fails. The registry holds no
# npm-audit waiver right now -- WVR-007 was retired when the override on
# @puppeteer/browsers took extract-zip out of the graph -- and the gate's
# boundary stays under test against a fixture registry regardless.
security-npm:
	npm audit --json | .venv/bin/python scripts/check_npm_audit.py

security-osv:
	.tools/osv-scanner --lockfile uv.lock

security-secrets:
	.tools/gitleaks detect --source . --redact --exit-code 1

security-semgrep:
	uvx --python 3.12 --from semgrep==1.168.0 semgrep scan \
		--config p/default --config p/python --severity ERROR --error --metrics off

security-workflows:
	uvx --python 3.12 --from zizmor==1.16.3 zizmor .github/workflows/

security:
	@MAKE="$(MAKE)" scripts/run_gates.sh $(SECURITY_GATES)

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

compat:
	.venv/bin/python scripts/generate_workflow_compat_fixtures.py --check

verify:
	@MAKE="$(MAKE)" scripts/run_gates.sh $(VERIFY_GATES)

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

container-build:
	docker build --pull --tag outcome-receipts:local .

container-smoke: container-build
	docker run --rm --read-only --network none --cap-drop ALL \
		--security-opt no-new-privileges --tmpfs /tmp:rw,noexec,nosuid,size=16m \
		outcome-receipts:local --version

container-scan: container-build
	@set -eu; \
		image_tar=$$(mktemp "$${TMPDIR:-/tmp}/outcome-receipts-image.XXXXXX.tar"); \
		trap 'rm -f "$$image_tar"' EXIT; \
		docker save --output "$$image_tar" outcome-receipts:local; \
		docker run --rm \
			--volume "$$image_tar:/scan/image.tar:ro" \
			--volume outcome-receipts-trivy-cache:/root/.cache/trivy \
			aquasec/trivy:0.72.0@sha256:cffe3f5161a47a6823fbd23d985795b3ed72a4c806da4c4df16266c02accdd6f \
			image --input /scan/image.tar --scanners vuln \
			--severity HIGH,CRITICAL --exit-code 1 --ignore-unfixed=false

container-verify: container-smoke container-scan

# One-command offline demo after the image is built. The host UID/GID owns the
# generated files; the runtime has no network, capabilities, or writable root.
container-demo: container-build
	mkdir -p out/container
	docker run --rm --read-only --network none --cap-drop ALL \
		--security-opt no-new-privileges --tmpfs /tmp:rw,noexec,nosuid,size=16m \
		--user "$$(id -u):$$(id -g)" --volume "$(CURDIR):/workspace" \
		outcome-receipts:local run \
		--config examples/housing-demo/report.toml \
		--out out/container --ledger out/container/export-ledger.jsonl \
		--approved-by "Container demo" --reproducible

clean:
	rm -rf out .pytest_cache .mypy_cache .ruff_cache .lighthouseci
