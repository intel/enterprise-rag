#!/bin/sh
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Node topology probe — runs inside a busybox pod (via k8s exec) and emits a
# single JSON line describing the host's CPU/NUMA/memory topology.
#
# Reads only /sys and /proc. No lscpu, no bash-isms — busybox sh + awk only.
#
# Output shape (consumed by calculate_replicas.py + install.yaml VLLM bind
# list assembly):
#   {"numa_nodes":N,"cpus_per_numa_node":M,"total_memory_GiB":G,
#    "amx_supported":true|false,
#    "physical_cpus_per_numa":{"0":"0,1,2,...","1":"..."}}
#
# `physical_cpus_per_numa` lists only PRIMARY threads (the lowest CPU id in
# each core's thread_siblings_list) so a caller taking pool[0:N] gets N
# distinct physical cores, not colliding HT siblings. Numeric-sorted per
# NUMA node — shell globs sort lexically ("cpu10" before "cpu2"), so we
# expand /sys/devices/system/node/nodeX/cpulist by hand.
#
# Kept out of the ansible YAML so Jinja never sees the shell braces/pipes.
set -eu

numa=$(ls -d /sys/devices/system/node/node[0-9]* 2>/dev/null | wc -l)
logical=$(ls -d /sys/devices/system/cpu/cpu[0-9]* 2>/dev/null | wc -l)
[ "$numa" -lt 1 ] && numa=1
cpn=$(( logical / numa ))
mem=$(awk '/MemTotal/ { print int($2/1024/1024) }' /proc/meminfo)

amx=false
grep -q -m1 ' amx' /proc/cpuinfo && amx=true

pcpus=''
sep=''
for nd in /sys/devices/system/node/node[0-9]*; do
    [ -d "$nd" ] || continue
    nid=$(basename "$nd" | sed 's/^node//')
    cpulist=$(cat "$nd/cpulist" 2>/dev/null || echo '')
    list=''
    for part in $(printf '%s' "$cpulist" | tr ',' ' '); do
        case "$part" in
            *-*) lo=${part%-*}; hi=${part#*-} ;;
            *)   lo=$part;      hi=$part      ;;
        esac
        cid=$lo
        while [ "$cid" -le "$hi" ]; do
            sibs=$(cat "/sys/devices/system/cpu/cpu${cid}/topology/thread_siblings_list" 2>/dev/null || echo "$cid")
            primary=$(printf '%s' "$sibs" | cut -d, -f1 | cut -d- -f1)
            if [ "$cid" = "$primary" ]; then
                if [ -z "$list" ]; then list="$cid"; else list="${list},${cid}"; fi
            fi
            cid=$((cid + 1))
        done
    done
    pcpus="${pcpus}${sep}\"${nid}\":\"${list}\""
    sep=','
done

printf '{"numa_nodes":%d,"cpus_per_numa_node":%d,"total_memory_GiB":%d,"amx_supported":%s,"physical_cpus_per_numa":{%s}}\n' \
    "$numa" "$cpn" "$mem" "$amx" "$pcpus"
