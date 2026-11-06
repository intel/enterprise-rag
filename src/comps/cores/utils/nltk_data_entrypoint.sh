#!/bin/sh
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# NLTK (>= 3.10.4) only trusts a data directory owned by the running UID or by
# root and not writable by group or others. The images bake their NLTK data
# owned by UID 1000. When the container runs as another UID, as OpenShift's
# restricted-v2 SCC does, copy the data to a directory that UID owns and point
# NLTK at it. As UID 1000, or with NLTK_DATA already set, nothing changes.

baked="/home/user/.venv/nltk_data"

if [ -d "$baked" ] && [ ! -O "$baked" ] && [ -z "${NLTK_DATA:-}" ]; then
    copy="${TMPDIR:-/tmp}/nltk_data"
    if rm -rf "$copy" && mkdir -p "$copy" && cp -R "$baked/." "$copy/" && chmod -R go-w "$copy"; then
        export NLTK_DATA="$copy"
    else
        echo "nltk_data_entrypoint: could not copy $baked to $copy; NLTK will refuse it as UID $(id -u)" >&2
    fi
fi

exec "$@"
