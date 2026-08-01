# syntax=docker/dockerfile:1.7

# Both build inputs are immutable multi-architecture indexes. Dependabot or
# Renovate may refresh the tag and digest together after CI rebuilds and scans.
FROM ghcr.io/astral-sh/uv:0.11.19@sha256:b46b03ddfcfbf8f547af7e9eaefdf8a39c8cebcba7c98858d3162bd28cf536f6 AS uv
FROM python:3.13-alpine@sha256:399babc8b49529dabfd9c922f2b5eea81d611e4512e3ed250d75bd2e7683f4b0 AS build

COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /opt/outcome-receipts

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13-alpine@sha256:399babc8b49529dabfd9c922f2b5eea81d611e4512e3ed250d75bd2e7683f4b0

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
