// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { keycloakService } from "@intel-enterprise-rag-ui/auth";
import {
  selectIsChatSidebarOpen,
  toggleChatSidebar,
} from "@intel-enterprise-rag-ui/chat";
import {
  AppHeaderProps,
  SidePanelFooter,
  SidePanelHeader,
} from "@intel-enterprise-rag-ui/layouts";

import ViewSwitchButton from "@/components/ViewSwitchButton/ViewSwitchButton";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { resetStore } from "@/store/utils";
import { getChatQnAAppEnv } from "@/utils";

export const viewSwitchButton = <ViewSwitchButton />;

const APP_DISPLAY_NAME = "ChatQnA";
const PROJECT_NAME = "Intel® AI for Enterprise RAG";
const APP_VERSION =
  getChatQnAAppEnv("ERAG_VERSION") || import.meta.env.VITE_APP_VERSION;
const MAINTENANCE_MODE = getChatQnAAppEnv("MAINTENANCE_MODE");
const USER_GUIDE_URL = `https://github.com/opea-project/Enterprise-RAG/blob/release-${APP_VERSION}/docs/Intel_AI_for_Enterprise_RAG_ChatQnA_User_Guide.pdf`;

/** Side panel is now available on every route, not just chat — the toggle in the header-left is
 * unconditional, and the same `chatSidebar` open/closed state now covers the whole app. */
export const useSidebarState = () => {
  const isSidebarOpen = useAppSelector(selectIsChatSidebarOpen);
  const dispatch = useAppDispatch();
  return {
    isSidebarOpen,
    onToggleSidebar: () => dispatch(toggleChatSidebar()),
  };
};

export const useAppHeaderProps = (): AppHeaderProps => {
  const { isSidebarOpen, onToggleSidebar } = useSidebarState();

  return {
    maintenanceMode: MAINTENANCE_MODE === "true",
    isSidebarOpen,
    onToggleSidebar,
  };
};

/** Rendered as the side panel's own top header row — see SidePanelHeader. */
export const SidePanelHeaderContent = () => (
  <SidePanelHeader
    title={APP_DISPLAY_NAME}
    subtitle={`${PROJECT_NAME} v${APP_VERSION}`}
    appName={PROJECT_NAME}
    appVersion={APP_VERSION}
    userGuideUrl={USER_GUIDE_URL}
  />
);

/** Rendered in the side panel's footer (not the header) — see SidePanelFooter. */
export const SidePanelFooterContent = () => (
  <SidePanelFooter
    username={keycloakService.getUsername()}
    userEmail={keycloakService.getEmail()}
    onLogout={() => {
      resetStore();
      keycloakService.redirectToLogout();
    }}
  />
);
