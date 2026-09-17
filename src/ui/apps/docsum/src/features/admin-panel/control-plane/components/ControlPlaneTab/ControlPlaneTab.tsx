// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { keycloakService } from "@intel-enterprise-rag-ui/auth";
import {
  ControlPlaneTab,
  ServiceCard,
  ServiceData,
  useControlPlanePolling,
} from "@intel-enterprise-rag-ui/control-plane";
import { FitViewOptions, Node, NodeChange } from "@xyflow/react";
import { useCallback, useEffect, useMemo } from "react";

import {
  useChangeArgumentsMutation,
  useGetServicesDataQuery,
  useLazyGetServicesDataQuery,
} from "@/features/admin-panel/control-plane/api";
import {
  docSumGraphEdgesSelector,
  docSumGraphIsAutorefreshEnabledSelector,
  docSumGraphIsLoadingSelector,
  docSumGraphIsRenderableSelector,
  docSumGraphNodesSelector,
  docSumGraphSelectedServiceNodeSelector,
  onDocSumGraphNodesChange,
  setDocSumGraphIsAutorefreshEnabled,
  setDocSumGraphSelectedServiceNode,
} from "@/features/admin-panel/control-plane/store/docSumGraph.slice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

const DocSumControlPlaneTab = () => {
  useGetServicesDataQuery();

  const dispatch = useAppDispatch();
  const isLoading = useAppSelector(docSumGraphIsLoadingSelector);
  const isRenderable = useAppSelector(docSumGraphIsRenderableSelector);
  const isAutorefreshEnabled = useAppSelector(
    docSumGraphIsAutorefreshEnabledSelector,
  );
  const nodes = useAppSelector(docSumGraphNodesSelector);
  const edges = useAppSelector(docSumGraphEdgesSelector);

  const [getServicesData, { isFetching }] = useLazyGetServicesDataQuery();

  const handleAutorefreshChange = useCallback(
    (enabled: boolean) => {
      dispatch(setDocSumGraphIsAutorefreshEnabled(enabled));
    },
    [dispatch],
  );

  const handleRefresh = useCallback(() => {
    getServicesData();
  }, [getServicesData]);

  useControlPlanePolling(handleRefresh, isAutorefreshEnabled);

  useEffect(() => {
    return () => {
      dispatch(setDocSumGraphSelectedServiceNode([]));
    };
  }, [dispatch]);

  const handleSelectionChange = useCallback(
    ({ nodes }: { nodes: Node<Record<string, unknown>>[] }) => {
      dispatch(setDocSumGraphSelectedServiceNode(nodes as Node<ServiceData>[]));
    },
    [dispatch],
  );

  const handleNodesChange = (
    changes: NodeChange<Node<Record<string, unknown>>>[],
  ) => {
    dispatch(
      onDocSumGraphNodesChange(changes as NodeChange<Node<ServiceData>>[]),
    );
  };

  const fitViewOptions: FitViewOptions = useMemo(
    () => ({
      padding: 0.5,
    }),
    [],
  );

  return (
    // The graph is read-only: only nodes carry configurable params, so edges are
    // fixed and onEdgesChange/onConnect are intentionally omitted to keep the
    // topology non-editable.
    <ControlPlaneTab
      nodes={nodes}
      edges={edges}
      isLoading={isLoading}
      isRenderable={isRenderable}
      isAutorefreshEnabled={isAutorefreshEnabled}
      onAutorefreshChange={handleAutorefreshChange}
      onRefresh={handleRefresh}
      isFetching={isFetching}
      onNodesChange={handleNodesChange}
      onSelectionChange={handleSelectionChange}
      fitViewOptions={fitViewOptions}
      ConfigPanel={<DocSumServiceCard />}
    />
  );
};

const DocSumServiceCard = () => {
  const [changeArguments] = useChangeArgumentsMutation();
  const selectedServiceNode = useAppSelector(
    docSumGraphSelectedServiceNodeSelector,
  );

  const isReadOnly =
    keycloakService.isMaintainerUser() && !keycloakService.isAdminUser();

  return (
    <ServiceCard
      selectedServiceNode={selectedServiceNode}
      changeArguments={changeArguments}
      isReadOnly={isReadOnly}
    />
  );
};

export default DocSumControlPlaneTab;
