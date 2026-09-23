#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

CHUNK_SIZE = 512
CHUNK_OVERLAPPING = 64
DATAPREP_UPLOAD_DIR = "e2e/files/dataprep_upload"
AUDIO_OUTPUT_FILES_DIR = "e2e/files/audio_output"
TEST_AUDIO_DIR = "e2e/files/audio"
TEST_FILES_DIR = "e2e/files"
VITE_KEYCLOAK_REALM = "EnterpriseRAG"
VITE_KEYCLOAK_CLIENT_ID = "EnterpriseRAG-oidc"
INGRESS_NGINX_CONTROLLER_NS = "ingress-nginx"
INGRESS_NGINX_CONTROLLER_POD_LABEL_SELECTOR = {"app.kubernetes.io/name": "ingress-nginx"}
CHATQNA_NAMESPACE = "chatqna"
EDP_NAMESPACE = "edp"
LLM_INFERENCE_NAMESPACE = "llm-inference"

# Backup and restore. The engine lives in the installer; these mirror what it
# labels its objects with (roles/backup/defaults/main.yaml) and what
# deployment/backup_profile.yaml declares.
VELERO_NAMESPACE = "velero"
BACKUP_PROFILE_NAME = "erag"
BACKUP_PROFILE_LABEL = "ai-solutions.io/backup-profile"
BACKUP_VERSION_LABEL = "meta.erag/solution-version"
# Namespaces holding the data the lifecycle tests create. The profile captures
# more than these; a backup that misses one of these missed the test data.
# postgresql is here because the identity realm lives in a database in it, so the
# accounts the tests create are only recoverable if its volume was captured.
BACKED_UP_DATA_NAMESPACES = [
    "default", "postgresql", "seaweedfs", "vdb", "edp", "chat-history",
]
# The shared database the identity realm lives in.
IDENTITY_DATABASE_NAMESPACE = "postgresql"
