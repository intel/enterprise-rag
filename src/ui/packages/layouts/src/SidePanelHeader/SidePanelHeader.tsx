// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import "./SidePanelHeader.css";

import { AboutDialog } from "@/AboutDialog/AboutDialog";

export interface SidePanelHeaderProps {
  /** Primary line — the app's own display name (e.g. "ChatQnA") */
  title: string;
  /** Secondary line — the suite name and release version (e.g. "Intel® AI for Enterprise RAG v1.2.0") */
  subtitle: string;
  /** Suite name, passed through to the About dialog's own body content */
  appName: string;
  /** Suite version, passed through to the About dialog's own body content */
  appVersion: string;
  userGuideUrl?: string;
}

/**
 * First row inside the side panel — matches the app header's height. Pairs the app's identity
 * (title/subtitle) with the About dialog trigger, vertically centered on the right.
 */
export const SidePanelHeader = ({
  title,
  subtitle,
  appName,
  appVersion,
  userGuideUrl,
}: SidePanelHeaderProps) => (
  <div className="side-panel-header">
    <div className="side-panel-header__identity">
      <p className="side-panel-header__title">{title}</p>
      <p className="side-panel-header__subtitle">{subtitle}</p>
    </div>
    <AboutDialog
      appName={appName}
      appVersion={appVersion}
      userGuideUrl={userGuideUrl}
    />
  </div>
);
