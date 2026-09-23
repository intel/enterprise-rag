// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { keycloakService } from "@intel-enterprise-rag-ui/auth";
import { createChatHistoryApi } from "@intel-enterprise-rag-ui/chat";

export const chatHistoryApi = createChatHistoryApi(keycloakService);

export const {
  useGetAllChatsQuery,
  useLazyGetAllChatsQuery,
  useGetChatByIdQuery,
  useLazyGetChatByIdQuery,
  useSaveChatMutation,
  useChangeChatNameMutation,
  useDeleteChatMutation,
} = chatHistoryApi;
