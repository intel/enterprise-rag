// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { keycloakService } from "@intel-enterprise-rag-ui/auth";
import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";

import {
  DOCSUM_API_ENDPOINTS,
  ERROR_MESSAGES,
} from "@/features/docsum/api/config";
import {
  SummarizeFileRequest,
  SummarizePlainTextRequest,
  SummarizeResponse,
} from "@/features/docsum/api/types";
import {
  buildFileUploadFormData,
  handleSummaryStreamResponse,
} from "@/features/docsum/utils/api";
import { getErrorMessage } from "@/utils/api";

export const summarizationApi = createApi({
  reducerPath: "summarizationApi",
  baseQuery: fetchBaseQuery({
    baseUrl: DOCSUM_API_ENDPOINTS.BASE_URL,
    // No Content-Type here: the file upload posts FormData, whose boundary only the
    // browser can generate. fetchBaseQuery sets application/json for JSON bodies.
    prepareHeaders: async (headers: Headers) => {
      await keycloakService.refreshToken();
      headers.set("Authorization", `Bearer ${keycloakService.getToken()}`);
      return headers;
    },
  }),
  endpoints: (builder) => ({
    summarizePlainText: builder.mutation<
      SummarizeResponse,
      SummarizePlainTextRequest
    >({
      query: ({ text, summaryType, onSummaryUpdate }) => ({
        url: "",
        method: "POST",
        body: {
          texts: [text],
          // The router only forwards the `parameters` group to the pipeline steps,
          // so a summary type sent at the top level never reaches DocSum.
          ...(summaryType && { parameters: { summary_type: summaryType } }),
        },
        responseHandler: async (response) => {
          if (!response.ok) {
            // Rejecting here always surfaces as RTK Query's PARSING_ERROR shape,
            // which carries the real status as `originalStatus` and the response
            // body as `data` regardless of what's thrown — see getErrorMessage.
            return Promise.reject(
              new Error(`Request failed with status ${response.status}`),
            );
          }

          await handleSummaryStreamResponse(response, onSummaryUpdate);
        },
      }),
      transformErrorResponse: (error) =>
        getErrorMessage(error, ERROR_MESSAGES.SUMMARIZE_TEXT),
    }),
    summarizeFile: builder.mutation<SummarizeResponse, SummarizeFileRequest>({
      query: ({ file, summaryType, onSummaryUpdate }) => ({
        url: "",
        method: "POST",
        body: buildFileUploadFormData(file, summaryType),
        responseHandler: async (response) => {
          if (!response.ok) {
            // See the summarizePlainText responseHandler above: RTK Query reads
            // the real status/body independently regardless of what's thrown.
            return Promise.reject(
              new Error(`Request failed with status ${response.status}`),
            );
          }

          await handleSummaryStreamResponse(response, onSummaryUpdate);
        },
      }),
      transformErrorResponse: (error) =>
        getErrorMessage(error, ERROR_MESSAGES.SUMMARIZE_FILE),
    }),
  }),
});

export const { useSummarizePlainTextMutation, useSummarizeFileMutation } =
  summarizationApi;
