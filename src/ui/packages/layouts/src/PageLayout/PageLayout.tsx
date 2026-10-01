// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import "./PageLayout.css";

import classNames from "classnames";
import { PropsWithChildren, ReactNode } from "react";

import { AppHeader, AppHeaderProps } from "@/AppHeader/AppHeader";

interface PageLayoutProps extends PropsWithChildren {
  /** Props for the application header */
  appHeaderProps: AppHeaderProps;
  /** Configuration for the left sidebar */
  leftSidebar?: {
    /** Component to render in the left sidebar */
    component?: ReactNode;
    /** Whether the left sidebar is open */
    isOpen?: boolean;
  };
  /** Configuration for the right sidebar */
  rightSidebar?: {
    /** Component to render in the right sidebar */
    component?: ReactNode;
    /** Whether the right sidebar is open */
    isOpen?: boolean;
  };
}

/**
 * Page layout component for structuring application pages.
 * Supports header, left/right sidebars, and main content area.
 */
export const PageLayout = ({
  appHeaderProps,
  leftSidebar,
  rightSidebar,
  children,
}: PageLayoutProps) => {
  const { component: LeftSidebar, isOpen: isLeftSidebarOpen } =
    leftSidebar ?? {};
  const { component: RightSidebar, isOpen: isRightSidebarOpen } =
    rightSidebar ?? {};

  return (
    <div className="page-layout__root">
      <div
        className={classNames("page-layout__content", {
          "page-layout__content--left-sidebar-open": isLeftSidebarOpen,
          "page-layout__content--right-sidebar-open": isRightSidebarOpen,
        })}
      >
        <AppHeader {...appHeaderProps} />
        <main className="page-layout__main-outlet" id="main">
          {children}
        </main>
      </div>
      {isLeftSidebarOpen && LeftSidebar}
      {isRightSidebarOpen && RightSidebar}
    </div>
  );
};
