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
[[ -n $body ]] || { echo "usage: comment.sh <<'EOF' ... EOF" >&2; exit 2; }
gh issue comment "$issue" --body "$body"
