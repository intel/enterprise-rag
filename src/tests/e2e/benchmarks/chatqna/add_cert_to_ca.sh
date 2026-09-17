#!/bin/bash
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

domain=${ERAG_DOMAIN_NAME:-solutions.ai}

# Hostnames whose self-signed certs we want as trusted CAs.
# Keycloak runs on its own subdomain in the inference stack, so it
# presents a different cert than the main gateway and must be fetched
# separately.
hosts=(
    "${domain}"
    "keycloak.${domain}"
)

for host in "${hosts[@]}"; do
    randname=$(openssl rand -hex 16)
    if ! </dev/null openssl s_client -connect "${host}:443" -servername "${host}" 2>/dev/null \
            | openssl x509 > "/usr/local/share/ca-certificates/erag-cert-${randname}.crt"; then
        echo "WARN: failed to fetch cert for ${host}, skipping" >&2
        rm -f "/usr/local/share/ca-certificates/erag-cert-${randname}.crt"
    fi
done

update-ca-certificates
