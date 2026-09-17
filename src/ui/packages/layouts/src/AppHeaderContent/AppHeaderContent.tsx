// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { LogoutButton } from "@intel-enterprise-rag-ui/auth";
import {
  ColorSchemeSwitch,
  NewChatButton,
} from "@intel-enterprise-rag-ui/components";
import { ReactNode } from "react";

import { AboutDialog } from "@/AboutDialog/AboutDialog";
import { AppNameText } from "@/AppNameText/AppNameText";
import { SideMenuIconButton } from "@/SideMenu/SideMenu";
import { UsernameText } from "@/UsernameText/UsernameText";

export interface AppHeaderLeftSideContentProps {
  appName: string;
  maintenanceMode?: boolean;
  isChatRoute?: boolean;
  isChatSideMenuOpen?: boolean;
  onToggleChatSideMenu?: () => void;
}

export const AppHeaderLeftSideContent = ({
  appName,
  maintenanceMode,
  isChatRoute,
  isChatSideMenuOpen = false,
  onToggleChatSideMenu,
}: AppHeaderLeftSideContentProps) => {
  if (maintenanceMode) {
    return <AppNameText appName={appName} />;
  }

  return (
    <>
      {isChatRoute && onToggleChatSideMenu && (
        <SideMenuIconButton
          isSideMenuOpen={isChatSideMenuOpen}
          onPress={onToggleChatSideMenu}
        />
      )}
      <AppNameText appName={appName} />
    </>
  );
};

export interface AppHeaderRightSideContentProps {
  appName: string;
  appVersion: string;
  userGuideUrl: string;
  username: string;
  onLogout: () => void;
  onNewChat?: () => void;
  showNewChatButton?: boolean;
  renderViewSwitchButton?: ReactNode;
}

export const AppHeaderRightSideContent = ({
  appName,
  appVersion,
  userGuideUrl,
  username,
  onLogout,
  onNewChat,
  showNewChatButton,
  renderViewSwitchButton,
}: AppHeaderRightSideContentProps) => (
  <>
    {showNewChatButton && onNewChat && <NewChatButton onPress={onNewChat} />}
    {renderViewSwitchButton}
    <ColorSchemeSwitch />
    <AboutDialog
      appName={appName}
      appVersion={appVersion}
      userGuideUrl={userGuideUrl}
    />
    <UsernameText username={username} />
    <LogoutButton onPress={onLogout} />
  </>
);
