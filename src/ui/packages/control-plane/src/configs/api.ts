// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export const API_ENDPOINTS = {
  GET_DOCSUM_STATUS: "/api/v1/docsum/status",
  GET_AUDIO_STATUS: "/api/v1/audio/status",
  GET_CHATQNA_STATUS: "/api/v1/chatqna/status",
  GET_SERVICE_CONFIG: "/v1/system_fingerprint/config",
  CHANGE_ARGUMENTS: "/v1/system_fingerprint/change_arguments",
  POST_RETRIEVER_QUERY: "/api/v1/edp/retrieve",
} as const;

export const ERROR_MESSAGES = {
  GET_STATUS: "Failed to fetch services status",
  GET_SERVICES_PARAMETERS: "Failed to fetch services parameters",
  GET_SERVICES_DATA: "Failed to fetch services data",
  CHANGE_ARGUMENTS: "Failed to change service arguments",
  POST_RETRIEVER_QUERY: "Failed to fetch retrieved documents",
} as const;

// Node IDs shared by every pipeline that renders the standard RAG service
// chain (chatqna, audioqna). docsum's pipeline is a disjoint set and declares
// its own node IDs locally.
export const BASE_SERVICE_NODE_IDS = [
  "embedding_model_server",
  "embedding",
  "retriever",
  "vectordb",
  "reranker",
  "reranker_model_server",
  "prompt_template",
  "input_guard",
  "llm",
  "llm_model_server",
  "output_guard",
] as const;

// Service-name-to-node-ID entries shared by chatqna and audioqna. Each service
// maps to the node IDs it backs; every entry is an array so a service backing
// several instances of its kind lists a node ID per instance, single-instance
// services list one. audioqna extends this with its own audio-specific
// entries; docsum stays fully app-local.
export const BASE_SERVICE_NAME_NODE_ID_MAP: Record<
  string,
  (typeof BASE_SERVICE_NODE_IDS)[number][]
> = {
  "v1:tei-embedding-svc": ["embedding_model_server"],
  "v1:torchserve-embedding-svc": ["embedding_model_server"],
  "v1:vllm-embedding-svc": ["embedding_model_server"],
  "v1:ovms-embedding-svc": ["embedding_model_server"],
  "v1:mosec-embedding-svc": ["embedding_model_server"],
  "v1:embedding-svc": ["embedding"],
  "v1:retriever-svc": ["retriever"],
  "v1:redis-vector-db": ["vectordb"],
  "v1:reranking-svc": ["reranker"],
  "v1:tei-reranking-svc": ["reranker_model_server"],
  "v1:torchserve-reranking-svc": ["reranker_model_server"],
  "v1:prompt-template-svc": ["prompt_template"],
  "v1:input-scan-svc": ["input_guard"],
  "v1:llm-svc": ["llm"],
  "v1:vllm-service-m": ["llm_model_server"],
  "v1:output-scan-svc": ["output_guard"],
};
