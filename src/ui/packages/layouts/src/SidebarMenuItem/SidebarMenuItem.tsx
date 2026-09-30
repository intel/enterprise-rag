// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import "./SidebarMenuItem.css";

import { IconName } from "@intel-enterprise-rag-ui/icons";
import classNames from "classnames";
import { ReactNode } from "react";

import { SidebarNavItemContent } from "@/SidebarNav/SidebarNavItemContent";

interface SidebarMenuItemProps {
  /** Icon shown at the start of the row */
  icon?: IconName;
  /** Row label */
  label: string;
  /** Rendered at the end of the row, e.g. a disclosure chevron */
  trailing?: ReactNode;
  /** Highlights the row, matching a SidebarNav link's active state */
  isActive?: boolean;
  onPress: () => void;
  "aria-label"?: string;
  "aria-expanded"?: boolean;
  "data-testid"?: string;
}

/**
 * A single sidebar row (icon + label + optional trailing element) on a plain button, styled
 * identically to SidebarNav's own rows (`.sidebar-nav__link`). Use this for any standalone sidebar
 * action — e.g. New Chat — that isn't a route link but should still look like it belongs to the
 * same list as the admin-panel nav items.
 */
export const SidebarMenuItem = ({
  icon,
  label,
  trailing,
  isActive = false,
  onPress,
  "aria-label": ariaLabel,
  "aria-expanded": ariaExpanded,
  "data-testid": dataTestId,
}: SidebarMenuItemProps) => (
  <button
    type="button"
    onClick={onPress}
    aria-label={ariaLabel ?? label}
    aria-expanded={ariaExpanded}
    data-testid={dataTestId}
    className={classNames("sidebar-nav__link sidebar-nav__link--toggle", {
      "sidebar-nav__link--active": isActive,
    })}
  >
    <SidebarNavItemContent icon={icon} label={label} trailing={trailing} />
  </button>
);
