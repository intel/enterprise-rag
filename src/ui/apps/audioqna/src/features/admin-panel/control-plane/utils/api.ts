// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  BASE_SERVICE_NAME_NODE_ID_MAP,
  BASE_SERVICE_NODE_IDS,
} from "@intel-enterprise-rag-ui/control-plane";

export const SERVICE_NODE_IDS = [
  ...BASE_SERVICE_NODE_IDS,
  "asr",
  "vllm-audio-cpu",
  "tts",
  "tts-model-server",
] as const;

// Each service maps to the node IDs it backs. Every entry is an array so a
// service backing several instances of its kind lists a node ID per instance;
// single-instance services list one.
export const SERVICE_NAME_NODE_ID_MAP: Record<
  string,
  (typeof SERVICE_NODE_IDS)[number][]
> = {
  ...BASE_SERVICE_NAME_NODE_ID_MAP,
  "v1:asr-svc": ["asr"],
  "v1:tts-svc": ["tts"],
  "v1:tts-fastapi-model-server": ["tts-model-server"],
  "v1:vllm-audio-cpu": ["vllm-audio-cpu"],
};
