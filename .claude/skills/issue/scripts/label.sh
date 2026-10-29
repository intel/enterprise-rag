#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
export GH_REPO="$GITHUB_REPOSITORY"
issue=$(jq -r '.issue.number' "$GITHUB_EVENT_PATH")
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
