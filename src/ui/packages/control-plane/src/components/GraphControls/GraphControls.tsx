// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import "./GraphControls.css";

import { ConfigurableServiceIcon } from "@intel-enterprise-rag-ui/icons";

import { ServiceStatusIndicator } from "@/components/ServiceStatusIndicator/ServiceStatusIndicator";
import { ServiceStatus } from "@/types/index";

export const GraphControls = () => {
  return (
    <div className="graph-controls" data-testid="graph-controls">
      <div className="graph-controls__legend">
        <div className="graph-controls__legend-item">
          <ServiceStatusIndicator status={ServiceStatus.Ready} noTooltip />
          <p className="graph-controls__legend-label">Ready</p>
        </div>
        <div className="graph-controls__legend-item">
          <ServiceStatusIndicator status={ServiceStatus.NotReady} noTooltip />
          <p className="graph-controls__legend-label">Not Ready</p>
        </div>
        <div className="graph-controls__legend-item">
          <ServiceStatusIndicator
            status={ServiceStatus.NotAvailable}
            noTooltip
          />
          <p className="graph-controls__legend-label">Status Not Available</p>
        </div>
        <div className="graph-controls__legend-item">
          <ConfigurableServiceIcon fontSize={12} />
          <p className="graph-controls__legend-label">Configurable Service</p>
        </div>
      </div>
    </div>
  );
};
