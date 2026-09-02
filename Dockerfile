# syntax=docker/dockerfile:1.7

# Both build inputs are immutable multi-architecture indexes. Dependabot or
# Renovate may refresh the tag and digest together after CI rebuilds and scans.
FROM ghcr.io/astral-sh/uv:0.11.19@sha256:b46b03ddfcfbf8f547af7e9eaefdf8a39c8cebcba7c98858d3162bd28cf536f6 AS uv
FROM python:3.13-alpine@sha256:540c7d91f98ff6880174c40e99067bf5941eb54d818a7a5e094d188b196a934d AS build

COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /opt/outcome-receipts

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
RUN uv sync --locked --no-dev --no-editable

FROM python:3.13-alpine@sha256:540c7d91f98ff6880174c40e99067bf5941eb54d818a7a5e094d188b196a934d

# Even the newest python:3.13-alpine rebuild still ships libcrypto3/libssl3
# 3.5.7-r0, which container-scan flags for CVE-2026-14456 (HIGH). Alpine v3.24
# main already carries the fixed 3.5.8-r0 build, so install it explicitly,
# version-pinned to keep the image deterministic rather than a floating
# "apk upgrade". Drop both pins, and this comment, once the base image itself
# ships 3.5.8-r0 or later; the pinned add will start failing when v3.24 main
# rotates the version out, which is the reminder to do exactly that.
RUN apk add --no-cache libcrypto3=3.5.8-r0 libssl3=3.5.8-r0

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
