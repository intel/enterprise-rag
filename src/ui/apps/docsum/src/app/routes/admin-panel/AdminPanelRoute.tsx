// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { keycloakService } from "@intel-enterprise-rag-ui/auth";
import {
  AdminPanelRoute,
  AdminTab,
  TelemetryAuthenticationTab,
} from "@intel-enterprise-rag-ui/layouts";
import { useMemo } from "react";

import {
  AppHeaderLeftSideContent,
  AppHeaderRightSideContent,
} from "@/components/AppHeaderContent/AppHeaderContent";
import ControlPlaneTab from "@/features/admin-panel/control-plane/components/ControlPlaneTab/ControlPlaneTab";
import { getDocSumAppEnv } from "@/utils";

const adminPanelTabs: AdminTab[] = [
  {
    name: "Control Plane",
    path: "control-plane",
    id: "control-plane",
    panel: <ControlPlaneTab />,
  },
  {
    name: "Telemetry & Authentication",
    path: "telemetry-authentication",
    id: "telemetry-authentication",
    panel: (
      <TelemetryAuthenticationTab
        grafanaDashboardUrl={getDocSumAppEnv("GRAFANA_DASHBOARD_URL")}
        keycloakAdminPanelUrl={getDocSumAppEnv("KEYCLOAK_ADMIN_PANEL_URL")}
      />
    ),
  },
];

const DocSumAdminPanelRoute = () => {
  const appHeaderProps = useMemo(
    () => ({
      leftSideContent: <AppHeaderLeftSideContent />,
      rightSideContent: <AppHeaderRightSideContent />,
    }),
    [],
  );

  return (
    <AdminPanelRoute
      tabs={adminPanelTabs}
      appHeaderProps={appHeaderProps}
      lastSelectedAdminTab=""
      onAdminTabChange={() => {}}
      isMaintainerOnly={
        keycloakService.isMaintainerUser() && !keycloakService.isAdminUser()
      }
      headerTestId="admin-panel-tabs"
    />
  );
};

export default DocSumAdminPanelRoute;
