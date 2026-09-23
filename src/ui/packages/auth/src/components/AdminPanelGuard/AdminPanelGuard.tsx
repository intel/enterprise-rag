// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { PropsWithChildren } from "react";
import { Navigate } from "react-router-dom";

import { KeycloakService } from "@/service/keycloak";

interface AdminPanelGuardProps extends PropsWithChildren {
  redirectTo: string;
  keycloakService: KeycloakService;
}

const AdminPanelGuard = ({
  children,
  redirectTo,
  keycloakService,
}: AdminPanelGuardProps) => {
  if (!keycloakService.isAdminUser() && !keycloakService.isMaintainerUser()) {
    return <Navigate to={redirectTo} replace />;
  }
  return children;
};

export { AdminPanelGuard };
