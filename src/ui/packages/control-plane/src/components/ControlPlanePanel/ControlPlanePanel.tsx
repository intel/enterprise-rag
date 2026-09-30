// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import "@xyflow/react/dist/style.css";
import "./ControlPlanePanel.css";

import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
  IconButton,
  LoadingFallback,
  Tooltip,
} from "@intel-enterprise-rag-ui/components";
import { ReactNode, useCallback, useEffect, useState } from "react";

import { GraphControls } from "@/components/GraphControls/GraphControls";

interface ControlPlanePanelProps {
  isLoading: boolean;
  isRenderable: boolean;
  Graph: ReactNode;
  ConfigPanel?: ReactNode;
  // True once a node is selected whose service ServiceCard can't render a config form for
  // (or no node is selected at all) — disables the trigger instead of opening an empty card.
  isConfigPanelDisabled?: boolean;
  onConfigPanelToggle?: (isVisible: boolean) => void;
}

export const ControlPlanePanel = ({
  isLoading,
  isRenderable,
  Graph,
  ConfigPanel,
  isConfigPanelDisabled = false,
  onConfigPanelToggle,
}: ControlPlanePanelProps) => {
  // Minimized (closed) by default — the config panel is one persistent floating card
  // docked top-right over the graph, whose own header carries the open/minimize control
  // (like a floating window's corner control), not a docked panel that reserves graph
  // width or a separate trigger-plus-popover pair.
  const [isConfigPanelVisible, setIsConfigPanelVisible] = useState(false);

  const toggleConfigPanel = useCallback(() => {
    const newVisibility = !isConfigPanelVisible;
    setIsConfigPanelVisible(newVisibility);
    onConfigPanelToggle?.(newVisibility);
  }, [isConfigPanelVisible, onConfigPanelToggle]);

  // Selection can change (or clear) while the card is open — close it rather than leave it
  // floating over a now-disabled trigger.
  useEffect(() => {
    if (isConfigPanelDisabled && isConfigPanelVisible) {
      setIsConfigPanelVisible(false);
      onConfigPanelToggle?.(false);
    }
  }, [isConfigPanelDisabled, isConfigPanelVisible, onConfigPanelToggle]);

  const getControlPlaneContent = () => {
    if (isLoading) {
      return <LoadingFallback />;
    } else {
      if (isRenderable) {
        return (
          <>
            <GraphControls />
            {Graph}
          </>
        );
      } else {
        return (
          <div className="control-plane-panel__not-renderable">
            <p>Pipeline graph cannot be rendered</p>
          </div>
        );
      }
    }
  };

  const toggleButtonLabel = isConfigPanelDisabled
    ? "Select a configurable service to view its configuration"
    : isConfigPanelVisible
      ? "Hide config panel"
      : "Show config panel";

  return (
    <div className="control-plane-panel" data-testid="control-plane-panel">
      <div className="control-plane-panel__dots-bg" aria-hidden="true" />
      <div className="graph-wrapper">{getControlPlaneContent()}</div>
      {ConfigPanel && (
        <Card
          size="sm"
          className="config-panel-card"
          data-testid="config-panel-card"
        >
          <CardHeader className="config-panel-card__header">
            {isConfigPanelVisible && (
              <CardTitle>Service Configuration</CardTitle>
            )}
            <CardAction>
              <Tooltip
                title={toggleButtonLabel}
                placement="left"
                trigger={
                  <IconButton
                    icon={isConfigPanelVisible ? "panel-hide" : "panel-show"}
                    size="sm"
                    onPress={toggleConfigPanel}
                    isDisabled={isConfigPanelDisabled}
                    aria-label={toggleButtonLabel}
                    aria-expanded={isConfigPanelVisible}
                    data-testid="config-panel-toggle-button"
                  />
                }
              />
            </CardAction>
          </CardHeader>
          {isConfigPanelVisible && (
            <CardContent
              className="config-panel-card__body"
              data-testid="config-panel-body"
            >
              {ConfigPanel}
            </CardContent>
          )}
        </Card>
      )}
    </div>
  );
};
