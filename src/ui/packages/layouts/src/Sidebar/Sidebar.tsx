// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import "./Sidebar.css";

import { IconButton, Tooltip } from "@intel-enterprise-rag-ui/components";
import classNames from "classnames";
import { PropsWithChildren, ReactNode } from "react";

type SidebarDirection = "left" | "right";

interface SidebarProps extends PropsWithChildren {
  /** Whether the sidebar is open */
  isOpen: boolean;
  /** Accessible label for navigation */
  ariaLabel?: string;
  /** Content to display in the header */
  headerContent?: ReactNode;
  /** Rendered in its own row above the scrollable content area, matching the app header's height */
  viewSwitchButton?: ReactNode;
  /** Content to display pinned to the bottom, below the scrollable content area */
  footerContent?: ReactNode;
  /** Direction of the sidebar (left or right) */
  direction?: SidebarDirection;
  /** Whether the sidebar has a header */
  hasHeader?: boolean;
}

/**
 * Sidebar navigation component for layout structure.
 * Supports left/right direction, header content, footer content, and open/close state.
 */
export const Sidebar = ({
  isOpen,
  ariaLabel,
  headerContent,
  viewSwitchButton,
  footerContent,
  direction = "right",
  hasHeader = false,
  children,
}: SidebarProps) => (
  <nav
    className={classNames("sidebar", {
      "sidebar--open": isOpen,
      "sidebar--closed": !isOpen,
      "sidebar--left": direction === "left",
      "sidebar--right": direction === "right",
    })}
    role="navigation"
    aria-label={ariaLabel}
    aria-hidden={!isOpen}
  >
    {isOpen && (
      <>
        {hasHeader && (
          <header className="sidebar__header">{headerContent}</header>
        )}
        {viewSwitchButton && (
          <div className="sidebar__view-switch">{viewSwitchButton}</div>
        )}
        <div className="sidebar__content">{children}</div>
        {footerContent && (
          <footer className="sidebar__footer">{footerContent}</footer>
        )}
      </>
    )}
  </nav>
);

interface SidebarToggleButtonProps {
  isSidebarOpen: boolean;
  sidebarTitle?: string;
  onPress: () => void;
}

export const SidebarToggleButton = ({
  isSidebarOpen,
  sidebarTitle,
  onPress,
}: SidebarToggleButtonProps) => {
  const label = `${isSidebarOpen ? "Close" : "Open"} ${sidebarTitle || "Sidebar"}`;

  return (
    <Tooltip
      title={label}
      trigger={
        <IconButton
          data-testid="sidebar-toggle-button"
          icon="sidebar-toggle"
          aria-label={label}
          onPress={onPress}
        />
      }
      placement="bottom"
    />
  );
};
