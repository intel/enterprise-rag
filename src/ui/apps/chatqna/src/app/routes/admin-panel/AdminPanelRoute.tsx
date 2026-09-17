// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { keycloakService } from "@intel-enterprise-rag-ui/auth";
import { DataIngestionTab } from "@intel-enterprise-rag-ui/data-ingestion";
import {
  AdminPanelRoute,
  AdminTab,
  TelemetryAuthenticationTab,
} from "@intel-enterprise-rag-ui/layouts";
import { useMemo } from "react";

import {
  appApi,
  selectAppApi,
  useGetFilePresignedUrlMutation,
  useLazyDownloadFileQuery,
} from "@/api";
import {
  AppHeaderLeftSideContent,
  AppHeaderRightSideContent,
} from "@/components/AppHeaderContent/AppHeaderContent";
import ControlPlaneTab from "@/features/admin-panel/control-plane/components/ControlPlaneTab/ControlPlaneTab";
import {
  useDeleteFileMutation,
  usePostFileMutation,
} from "@/features/admin-panel/data-ingestion/api/s3Api";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import {
  selectLastSelectedAdminTab,
  setLastSelectedAdminTab,
} from "@/store/viewNavigation.slice";
import { AppEnvKey } from "@/types";
import { getChatQnAAppEnv } from "@/utils";

const ChatQnAAdminPanelRoute = () => {
  const dispatch = useAppDispatch();
  const lastSelectedAdminTab = useAppSelector(selectLastSelectedAdminTab);

  const [getFilePresignedUrl] = useGetFilePresignedUrlMutation();
  const [downloadFile] = useLazyDownloadFileQuery();
  const [deleteFile] = useDeleteFileMutation();
  const [postFile] = usePostFileMutation();
  const appApiState = useAppSelector(selectAppApi);
  const appApiErrors = [
    ...Object.values(appApiState.queries).map((q) => q?.error),
    ...Object.values(appApiState.mutations).map((m) => m?.error),
  ];

  const appHeaderProps = useMemo(
    () => ({
      leftSideContent: <AppHeaderLeftSideContent />,
      rightSideContent: <AppHeaderRightSideContent />,
    }),
    [],
  );

  const adminPanelTabs: AdminTab[] = [
    {
      name: "Control Plane",
      path: "control-plane",
      id: "control-plane",
      panel: <ControlPlaneTab />,
    },
    {
      name: "Data Ingestion",
      path: "data-ingestion",
      id: "data-ingestion",
      panel: (
        <DataIngestionTab
          getAppEnv={(key) => getChatQnAAppEnv(key as AppEnvKey)}
          getFilePresignedUrl={getFilePresignedUrl}
          downloadFile={downloadFile}
          deleteFile={deleteFile}
          postFile={postFile}
          appApiErrors={appApiErrors}
          onResetAppApiState={() => dispatch(appApi.util.resetApiState())}
        />
      ),
    },
    {
      name: "Telemetry & Authentication",
      path: "telemetry-authentication",
      id: "telemetry-authentication",
      panel: (
        <TelemetryAuthenticationTab
          grafanaDashboardUrl={getChatQnAAppEnv("GRAFANA_DASHBOARD_URL")}
          keycloakAdminPanelUrl={getChatQnAAppEnv("KEYCLOAK_ADMIN_PANEL_URL")}
        />
      ),
    },
  ];

  return (
    <AdminPanelRoute
      tabs={adminPanelTabs}
      appHeaderProps={appHeaderProps}
      lastSelectedAdminTab={lastSelectedAdminTab}
      onAdminTabChange={(path) => dispatch(setLastSelectedAdminTab(path))}
      isMaintainerOnly={
        keycloakService.isMaintainerUser() && !keycloakService.isAdminUser()
      }
      headerTestId="admin-panel-tabs"
    />
  );
};

export default ChatQnAAdminPanelRoute;
