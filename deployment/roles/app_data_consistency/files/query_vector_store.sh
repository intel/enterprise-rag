#!/bin/sh
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Sums DBSIZE over the master nodes of the Redis cluster and prints the total on
# the last line as DATA_COUNT=<n>. redis-cli reads the password from
# REDISCLI_AUTH, so it is never a command-line argument. Any unreachable node or
# unparsable answer exits non-zero, which fails the Job rather than reporting a
# short count.
#
# Every command output is captured before it is trimmed: this shell has no
# pipefail, so a pipeline would report the exit status of the trimming command
# and hide an unreachable node.
set -eu

total=0
i=0
while [ "$i" -lt "$CLUSTER_NODES" ]; do
  node="${POD_BASENAME}-${i}.${HEADLESS_SERVICE}.${NAMESPACE}.svc.cluster.local"

  role_output=$(redis-cli -h "$node" -p "$REDIS_PORT" ROLE)
  role=$(printf '%s\n' "$role_output" | head -n 1 | tr -d '\r')

  if [ "$role" = "master" ]; then
    size_output=$(redis-cli -h "$node" -p "$REDIS_PORT" DBSIZE)
    size=$(printf '%s' "$size_output" | tr -d '[:space:]')
    case "$size" in
      '' | *[!0-9]*)
        echo "unexpected DBSIZE from ${node}: '${size}'" >&2
        exit 1
        ;;
    esac
    echo "${node} is a master holding ${size} keys"
    total=$((total + size))
  else
    echo "${node} is a ${role}, not counted"
  fi

  i=$((i + 1))
done

echo "DATA_COUNT=${total}"
