// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { KeycloakEnvKey } from "@intel-enterprise-rag-ui/auth";
import { BaseAppEnvKey } from "@intel-enterprise-rag-ui/utils";

export type AppEnvKey =
  | BaseAppEnvKey
  | KeycloakEnvKey
  | "S3_URL"
  | "S3_SEND_BEARER_TOKEN"
  | "CHAT_DISCLAIMER_TEXT"
  | "MAINTENANCE_MODE"
  | "MAINTENANCE_MODE_REASON"
  | "NER_ENABLED"
  | "EMBEDDING_MODEL_MIGRATION_REQUIRED"
  | "EMBEDDING_MODEL_MIGRATION_OLD_MODEL"
  | "EMBEDDING_MODEL_MIGRATION_NEW_MODEL";
