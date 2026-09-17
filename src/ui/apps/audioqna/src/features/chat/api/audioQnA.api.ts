// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { keycloakService } from "@intel-enterprise-rag-ui/auth";
import { createQnAApi, QnAApiConfig } from "@intel-enterprise-rag-ui/chat";

const AUDIO_QNA_API_CONFIG: QnAApiConfig = {
  postPromptEndpoint: "/api/v1/chatqna",
  reducerPath: "audioQnAApi",
};

export const audioQnAApi = createQnAApi(keycloakService, AUDIO_QNA_API_CONFIG);

export const { usePostPromptMutation } = audioQnAApi;
