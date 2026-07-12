#!/usr/bin/env bash
set -euo pipefail

repository="${1:-ChelseaKR/outcome-receipts}"
captured_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

jq -n \
  --arg captured_at "$captured_at" \
  --arg repository "$repository" \
  --argjson views "$(gh api "repos/$repository/traffic/views")" \
  --argjson clones "$(gh api "repos/$repository/traffic/clones")" \
  --argjson referrers "$(gh api "repos/$repository/traffic/popular/referrers")" \
  --argjson paths "$(gh api "repos/$repository/traffic/popular/paths")" \
  --argjson repository_state "$(gh repo view "$repository" --json stargazerCount,forkCount,watchers)" \
  '{
    captured_at: $captured_at,
    repository: $repository,
    repository_state: $repository_state,
    views: $views,
    clones: $clones,
    referrers: $referrers,
    popular_paths: $paths
  }'
