// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Tab, TabId, Tabs } from "@intel-enterprise-rag-ui/components";
import { useEffect, useMemo, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { AppHeaderProps } from "@/AppHeader/AppHeader";
import { PageLayout } from "@/PageLayout/PageLayout";

export interface AdminTab extends Tab {
  path: string;
}

export interface AdminPanelRouteProps {
  tabs: AdminTab[];
  appHeaderProps?: AppHeaderProps;
  lastSelectedAdminTab: string;
  onAdminTabChange: (path: string) => void;
  isMaintainerOnly?: boolean;
  headerTestId?: string;
}

export const AdminPanelRoute = ({
  tabs,
  appHeaderProps,
  lastSelectedAdminTab,
  onAdminTabChange,
  isMaintainerOnly = false,
  headerTestId,
}: AdminPanelRouteProps) => {
  const visibleTabs = useMemo(
    () =>
      isMaintainerOnly
        ? tabs.filter((tab) => tab.id !== "telemetry-authentication")
        : tabs,
    [tabs, isMaintainerOnly],
  );

  const navigate = useNavigate();
  const location = useLocation();

  // Derive selected tab directly from URL — no state, no extra render cycle
  const selectedTab = useMemo<TabId>(() => {
    const path = location.pathname.split("/").pop();
    const tab = visibleTabs.find((tab) => tab.path === path);
    return (
      (tab?.id as TabId) ??
      (lastSelectedAdminTab as TabId) ??
      visibleTabs[0].path
    );
  }, [location.pathname, visibleTabs, lastSelectedAdminTab]);

  // Stable ref so onAdminTabChange never needs to be an effect dep
  const onAdminTabChangeRef = useRef(onAdminTabChange);
  onAdminTabChangeRef.current = onAdminTabChange;

  // Side effects only: notify parent of active tab, redirect on invalid path
  useEffect(() => {
    const path = location.pathname.split("/").pop();
    const tab = visibleTabs.find((tab) => tab.path === path);
    if (tab !== undefined) {
      onAdminTabChangeRef.current(tab.path);
    } else {
      const defaultTab = visibleTabs.find(
        (t) => t.path === lastSelectedAdminTab,
      )
        ? lastSelectedAdminTab
        : visibleTabs[0].path;
      navigate(`/admin-panel/${defaultTab}`, { replace: true });
    }
  }, [location.pathname, visibleTabs, lastSelectedAdminTab, navigate]);

  const handleTabSelectionChange = (id: TabId) => {
    const tab = visibleTabs.find((tab) => tab.id === id);
    const queryParams = location.search;
    if (!tab) return;

    let to = `/admin-panel/${tab.path}`;
    if (queryParams) {
      to += queryParams;
    }
    navigate(to);
  };

  return (
    <PageLayout appHeaderProps={appHeaderProps}>
      <Tabs
        data-testid={headerTestId}
        tabs={visibleTabs}
        selectedTab={selectedTab}
        onSelectionChange={handleTabSelectionChange}
      />
    </PageLayout>
  );
};
