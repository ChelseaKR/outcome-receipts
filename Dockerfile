# syntax=docker/dockerfile:1.7

# Both build inputs are immutable multi-architecture indexes. Dependabot or
# Renovate may refresh the tag and digest together after CI rebuilds and scans.
FROM ghcr.io/astral-sh/uv:0.11.19@sha256:b46b03ddfcfbf8f547af7e9eaefdf8a39c8cebcba7c98858d3162bd28cf536f6 AS uv
FROM python:3.13-alpine@sha256:7415fbc3c9e4979cc717d92377ab2bc7b2b4a2af1ac03cc52b5f3f88efedaf3a AS build

COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /opt/outcome-receipts

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
RUN uv sync --locked --no-dev --no-editable

FROM python:3.13-alpine@sha256:7415fbc3c9e4979cc717d92377ab2bc7b2b4a2af1ac03cc52b5f3f88efedaf3a

# libuuid 2.42.1-r0 is flagged by container-scan for seven HIGH util-linux CVEs
# (CVE-2026-53612, -53613, -53614, -76642, -78408, -78409, -78410), which
# appeared between 2026-09-02, when `main` last scanned clean, and 2026-09-05.
# Nothing in this repository changed; the vulnerability database did. Alpine
# v3.24 main carries 2.42.3-r1, past the 2.42.3-r0 the advisories name, so it is
# installed explicitly and version-pinned to keep the image deterministic rather
# than a floating "apk upgrade". Drop the pin, and this comment, once the base
# image itself ships 2.42.3-r1 or later; the pinned add will start failing when
# v3.24 main rotates that version out, which is the reminder to do exactly that.
#
# libuuid lives in the Alpine layer, which the digest above shares byte for byte
# (sha256:55afa1ec...) with every python:3.13-alpine rebuild published so far, so
# no digest bump reaches it. The layer *above* it is what the bump above did
# reach: the pinned base now ships libcrypto3/libssl3 3.5.8-r0 itself, which is
# the exit condition the CVE-2026-14456 workaround recorded for itself, so its
# two pins are retired here rather than carried as permanent no-ops that would
# have broken the build whenever v3.24 rotated 3.5.8-r0 out.
RUN apk add --no-cache libuuid=2.42.3-r1

# The runtime is the copied venv and nothing else; pip exists in the base
# image only for interactive installs this image never performs, and pip's
# vendored dependency copies (msgpack, setuptools) are exactly what the
# scanner flags next. Deleting pip removes the code itself, not the report
# of it: an image that cannot install packages at runtime is also the more
# honest shape for an offline tool.
RUN rm -rf /usr/local/lib/python3.13/site-packages/pip \
    /usr/local/lib/python3.13/site-packages/pip-*.dist-info \
    /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.13

LABEL org.opencontainers.image.source="https://github.com/ChelseaKR/outcome-receipts" \
      org.opencontainers.image.description="Offline-first, receipted nonprofit outcome reporting" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV PATH="/opt/outcome-receipts/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=build /opt/outcome-receipts/.venv /opt/outcome-receipts/.venv

# A numeric, unprivileged identity works on Docker and rootless runtimes without
# adding an OS account. Operators can override it with their host UID/GID when
# writing to a bind mount.
WORKDIR /workspace
USER 65532:65532

ENTRYPOINT ["receipts"]
CMD ["--help"]
