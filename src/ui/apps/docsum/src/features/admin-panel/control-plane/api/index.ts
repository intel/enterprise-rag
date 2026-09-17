// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { keycloakService } from "@intel-enterprise-rag-ui/auth";
import {
  API_ENDPOINTS,
  createControlPlaneApi,
  DOCSUM_PARAMS_KEYS,
  ERROR_MESSAGES,
} from "@intel-enterprise-rag-ui/control-plane";

import {
  resetDocSumGraph,
  setDocSumGraphIsLoading,
  setDocSumGraphIsRenderable,
  setupDocSumGraph,
} from "@/features/admin-panel/control-plane/store/docSumGraph.slice";
import {
  SERVICE_NAME_NODE_ID_MAP,
  SERVICE_NODE_IDS,
} from "@/features/admin-panel/control-plane/utils/api";
import { getErrorMessage, transformErrorMessage } from "@/utils/api";

export const controlPlaneApi = createControlPlaneApi(keycloakService, {
  paramsKeys: DOCSUM_PARAMS_KEYS,
  statusEndpoints: [API_ENDPOINTS.GET_DOCSUM_STATUS],
  graphActions: {
    reset: resetDocSumGraph,
    setup: setupDocSumGraph,
    setLoading: setDocSumGraphIsLoading,
    setRenderable: setDocSumGraphIsRenderable,
  },
  serviceNameNodeIdMap: SERVICE_NAME_NODE_ID_MAP,
  serviceNodeIds: SERVICE_NODE_IDS,
  fallbackErrorMessage: ERROR_MESSAGES.GET_SERVICES_DATA,
  getErrorMessage: (error, fallback) => getErrorMessage(error, fallback),
  transformErrorMessage: (error, fallback) =>
    transformErrorMessage(error, fallback),
});

export const {
  useGetServicesDataQuery,
  useLazyGetServicesDataQuery,
  useChangeArgumentsMutation,
} = controlPlaneApi;
