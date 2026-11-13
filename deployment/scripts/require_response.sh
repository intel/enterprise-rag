#!/bin/bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Prints the response piped in on stdin and exits 1 when it is empty.
require_response() {
    local response
    response=$(cat)
    echo "$response"

    if [ -n "$response" ]; then
        echo "Test finished successfully"
    else
        echo "Test failed: empty or failed response" >&2
        exit 1
    fi
}
