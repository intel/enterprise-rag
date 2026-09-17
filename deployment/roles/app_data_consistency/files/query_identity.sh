#!/bin/bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Counts the users of one realm through the admin REST API and prints the total
# on the last line as DATA_COUNT=<n>.
#
# The admin password reaches curl on standard input as part of the form body,
# and the bearer token reaches it through a curl configuration file under /tmp.
# Neither is ever a command-line argument, so neither appears in the container's
# process arguments. The endpoint is the in-cluster Service, so no proxy
# variables are set.
set -euo pipefail

readonly TOKEN_CONFIG=/tmp/curl-token.conf

encoded_user=$(printf '%s' "$KEYCLOAK_ADMIN_USER" | jq -sRr @uri)
encoded_password=$(printf '%s' "$KEYCLOAK_ADMIN_PASSWORD" | jq -sRr @uri)

token_response=$(printf 'grant_type=password&client_id=admin-cli&username=%s&password=%s' \
  "$encoded_user" "$encoded_password" |
  curl -sS --fail-with-body -X POST \
    "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    --data-binary @-)

access_token=$(printf '%s' "$token_response" | jq -r '.access_token // empty')
if [ -z "$access_token" ]; then
  echo "no admin token returned by ${KEYCLOAK_URL}" >&2
  exit 1
fi

umask 077
printf 'header = "Authorization: Bearer %s"\n' "$access_token" >"$TOKEN_CONFIG"

count=$(curl -sS --fail-with-body -K "$TOKEN_CONFIG" -X GET \
  "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/users/count")
rm -f "$TOKEN_CONFIG"

count=$(printf '%s' "$count" | tr -d '[:space:]')
case "$count" in
  '' | *[!0-9]*)
    echo "unexpected user count for realm ${KEYCLOAK_REALM}: '${count}'" >&2
    exit 1
    ;;
esac

echo "DATA_COUNT=${count}"
