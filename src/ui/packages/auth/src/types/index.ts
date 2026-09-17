// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  KeycloakConfig,
  KeycloakInitOptions,
  KeycloakLoginOptions,
} from "keycloak-js";

export type KeycloakEnvKey =
  | "KEYCLOAK_URL"
  | "KEYCLOAK_REALM"
  | "KEYCLOAK_CLIENT_ID"
  | "ADMIN_RESOURCE_ROLE"
  | "MAINTAINER_RESOURCE_ROLE"
  | "USER_RESOURCE_ROLE";

export interface KeycloakServiceConfig {
  keycloakConfig: KeycloakConfig;
  loginOptions?: KeycloakLoginOptions;
  adminResourceRole?: string;
  maintainerResourceRole?: string;
  userResourceRole?: string;
  initOptions?: KeycloakInitOptions;
  minTokenValidity?: number;
  onRefreshTokenFailed?: () => void;
}
