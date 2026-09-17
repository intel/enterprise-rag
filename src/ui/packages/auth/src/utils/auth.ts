// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { KeycloakService } from "@/service/keycloak";
import { KeycloakEnvKey, KeycloakServiceConfig } from "@/types";

export const keycloakService = new KeycloakService();

export const initializeKeycloak = (
  onInitialized: () => void,
  getAppEnv: (key: KeycloakEnvKey) => string,
  onRefreshTokenFailed: () => void,
  redirectPath?: string,
) => {
  const config: KeycloakServiceConfig = {
    keycloakConfig: {
      url: getAppEnv("KEYCLOAK_URL"),
      realm: getAppEnv("KEYCLOAK_REALM"),
      clientId: getAppEnv("KEYCLOAK_CLIENT_ID"),
    },
    adminResourceRole: getAppEnv("ADMIN_RESOURCE_ROLE"),
    maintainerResourceRole: getAppEnv("MAINTAINER_RESOURCE_ROLE"),
    userResourceRole: getAppEnv("USER_RESOURCE_ROLE"),
    loginOptions: {
      redirectUri: redirectPath
        ? `${location.origin}${redirectPath}`
        : location.origin,
    },
    onRefreshTokenFailed,
  };
  keycloakService.setup(config);
  keycloakService.init(onInitialized);
};
