// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { PropsWithChildren } from "react";
import { Navigate } from "react-router-dom";

import { KeycloakService } from "@/service/keycloak";

interface AccessGuardProps extends PropsWithChildren {
  userRole?: string;
  keycloakService: KeycloakService;
}

const AccessGuard = ({
  children,
  userRole,
  keycloakService,
}: AccessGuardProps) => {
  const hasAccess =
    keycloakService.isAdminUser() ||
    keycloakService.isMaintainerUser() ||
    keycloakService.isUser() ||
    (userRole && keycloakService.hasResourceRole(userRole));

  if (!hasAccess) {
    return <Navigate to="/unauthorized" replace />;
  }

  return children;
};

export { AccessGuard };
