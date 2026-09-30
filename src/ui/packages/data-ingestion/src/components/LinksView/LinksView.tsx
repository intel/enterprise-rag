// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import "./LinksView.css";

import LinksDataTable from "@/components/LinksDataTable/LinksDataTable";

export interface LinksViewProps {
  getAppEnv: (key: string) => string | undefined;
}

export const LinksView = ({ getAppEnv }: LinksViewProps) => (
  <section className="links-view" data-testid="data-ingestion-links-view">
    <LinksDataTable getAppEnv={getAppEnv} />
  </section>
);

export default LinksView;
