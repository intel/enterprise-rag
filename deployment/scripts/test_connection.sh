#! /bin/bash
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -e
set -o pipefail

source "$(dirname "${BASH_SOURCE[0]}")/require_response.sh"

# Function to handle errors
error_handler() {
    local error_code="$?"
    local error_command="$BASH_COMMAND"
    printf '%s\n' "Error in command: '$error_command' with exit code $error_code" >&2
    exit "$error_code"
}

# Trap all error signals and runs the aboves error handler
trap 'error_handler' ERR

NAMESPACE=chatqna
CLIENT_POD=""
accessUrl=""

POD_EXISTS=$(kubectl get pod -n $NAMESPACE -l app=client-test -o jsonpath={.items..metadata.name})

if [ -z "$POD_EXISTS" ]; then
    kubectl apply -f client_test/client-test.yaml -n $NAMESPACE
fi

kubectl wait --for=condition=available --timeout=300s deployment/client-test -n $NAMESPACE

export CLIENT_POD=$(kubectl get pod -n $NAMESPACE -l app=client-test -o jsonpath={.items..metadata.name})
export accessUrl=$(kubectl get gmc -n $NAMESPACE -o jsonpath="{.items[?(@.metadata.name=='$NAMESPACE')].status.accessUrl}")


JSON_PAYLOAD='{
    "text": "What is AVX512?"
}'

echo "Connecting to the server through the pod $CLIENT_POD using URL $accessUrl..."

kubectl exec "$CLIENT_POD" -n $NAMESPACE -- \
    curl --no-buffer -sf $accessUrl -X POST -d "$JSON_PAYLOAD" -H 'Content-Type: application/json' | require_response
