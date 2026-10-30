#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
export GH_REPO="$GITHUB_REPOSITORY"
case "${1:-} ${2:-}" in
  "issue view")
    [[ $# -eq 3 && $3 =~ ^[0-9]+$ ]] || { echo "usage: gh.sh issue view <number>" >&2; exit 2; }
    gh issue view "$3" --json number,title,body,author,labels,createdAt,comments ;;
  "issue search")
    [[ $# -eq 3 && $3 != *:* ]] || { echo "usage: gh.sh issue search <words, no qualifiers>" >&2; exit 2; }
    gh issue list --state all --limit 10 --search "$3" --json number,title,state,labels,url ;;
  "pr search")
    [[ $# -eq 3 && $3 != *:* ]] || { echo "usage: gh.sh pr search <words, no qualifiers>" >&2; exit 2; }
    gh pr list --state merged --limit 10 --search "$3" --json number,title,mergedAt,url ;;
  "label list")
    [[ $# -eq 2 ]] || { echo "usage: gh.sh label list" >&2; exit 2; }
    gh label list --limit 200 --json name,description ;;
  *)
    echo "allowed: issue view <number> | issue search <words> | pr search <words> | label list" >&2; exit 2 ;;
esac
