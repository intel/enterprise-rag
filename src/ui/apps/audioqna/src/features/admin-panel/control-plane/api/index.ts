// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { keycloakService } from "@intel-enterprise-rag-ui/auth";
import {
  API_ENDPOINTS,
  CONTROL_PLANE_PARAMS_KEYS,
  createControlPlaneApi,
  ERROR_MESSAGES,
} from "@intel-enterprise-rag-ui/control-plane";

import {
  resetAudioQnAGraph,
  setAudioQnAGraphIsLoading,
  setAudioQnAGraphIsRenderable,
  setupAudioQnAGraph,
} from "@/features/admin-panel/control-plane/store/audioQnAGraph.slice";
import {
  SERVICE_NAME_NODE_ID_MAP,
  SERVICE_NODE_IDS,
} from "@/features/admin-panel/control-plane/utils/api";
import {
  getErrorMessage,
  mergeNamespaceStatuses,
  transformErrorMessage,
} from "@/utils/api";

export const controlPlaneApi = createControlPlaneApi(keycloakService, {
  paramsKeys: CONTROL_PLANE_PARAMS_KEYS,
  statusEndpoints: [
    API_ENDPOINTS.GET_AUDIO_STATUS,
    API_ENDPOINTS.GET_CHATQNA_STATUS,
  ],
  mergeStatusResponses: (responses) =>
    mergeNamespaceStatuses(responses[0], responses[1]),
  graphActions: {
    reset: resetAudioQnAGraph,
    setup: setupAudioQnAGraph,
    setLoading: setAudioQnAGraphIsLoading,
    setRenderable: setAudioQnAGraphIsRenderable,
  },
  serviceNameNodeIdMap: SERVICE_NAME_NODE_ID_MAP,
  serviceNodeIds: SERVICE_NODE_IDS,
  fallbackErrorMessage: ERROR_MESSAGES.GET_STATUS,
  getErrorMessage: (error, fallback) => getErrorMessage(error, fallback),
  transformErrorMessage: (error, fallback) =>
    transformErrorMessage(error, fallback),
});

export const {
  useGetServicesDataQuery,
  useLazyGetServicesDataQuery,
  useChangeArgumentsMutation,
  usePostRetrieverQueryMutation,
} = controlPlaneApi;
