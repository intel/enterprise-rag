#!/bin/sh
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Runs one counting query over TCP and prints the result on the last line as
# DATA_COUNT=<n>. libpq takes the host, port, database, user and password from
# the PG* environment variables, so no credential is a command-line argument.
# -w makes a missing password an immediate failure instead of a prompt.
set -eu

# Captured before it is trimmed: this shell has no pipefail, so a pipeline would
# report the exit status of tr and hide a failed query.
raw=$(psql -w -t -A -c "$COUNT_SQL")
count=$(printf '%s' "$raw" | tr -d '[:space:]')
case "$count" in
  '' | *[!0-9]*)
    echo "unexpected count from ${PGHOST}/${PGDATABASE}: '${count}'" >&2
    exit 1
    ;;
esac

echo "DATA_COUNT=${count}"
