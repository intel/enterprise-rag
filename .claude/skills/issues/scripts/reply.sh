#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
export GH_REPO="$GITHUB_REPOSITORY"
issue=$(jq -r '.issue.number' "$GITHUB_EVENT_PATH")
if [[ -n $(gh api "repos/$GH_REPO/issues/$issue/comments" --jq '.[] | select(.user.login == "github-actions[bot]") | .id') ]]; then
  echo "already triaged" >&2
  exit 0
fi
body=$(head -c 4000)
[[ -n $body ]] || { echo "usage: reply.sh [label ...] <<'EOF' comment EOF" >&2; exit 2; }
valid=$(gh label list --limit 200 --json name --jq '.[].name')
args=()
for label in "$@"; do
  case "$label" in wontfix|duplicate|stale|"good first issue") continue ;; esac
  if grep -qxF -- "$label" <<< "$valid"; then
    args+=(--add-label "$label")
  fi
done
if [[ ${#args[@]} -gt 0 ]]; then
  gh issue edit "$issue" "${args[@]}"
fi
gh issue comment "$issue" --body "$body"
