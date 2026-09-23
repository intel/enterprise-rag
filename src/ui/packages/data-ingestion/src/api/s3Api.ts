// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { keycloakService } from "@intel-enterprise-rag-ui/auth";
import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";

import { ERROR_MESSAGES } from "@/config/api";
import { PostFileRequest } from "@/types/api";
import { handleOnQueryStarted, transformErrorMessage } from "@/utils/api";

type S3ApiState = {
  queries: Record<string, { error?: unknown } | undefined>;
  mutations: Record<string, { error?: unknown } | undefined>;
};

export const selectS3ApiState = (state: unknown): S3ApiState =>
  (state as { s3Api: S3ApiState }).s3Api;

// Reset s3Api state action — stable because reducerPath is always "s3Api"
export const resetS3ApiStateAction = (): { type: string } => ({
  type: "s3Api/resetApiState",
});

export const createS3Api = (getS3SendBearerToken: () => string | undefined) => {
  const s3Api = createApi({
    reducerPath: "s3Api",
    baseQuery: fetchBaseQuery({
      prepareHeaders: (headers) => {
        const token = keycloakService.getToken();
        if (token && getS3SendBearerToken() === "true") {
          headers.set("Authorization", `Bearer ${token}`);
        }
        return headers;
      },
    }),
    endpoints: (builder) => ({
      postFile: builder.mutation<void, PostFileRequest>({
        query: ({ url, file }) => ({
          url,
          method: "PUT",
          body: file,
          headers: {
            "Content-Type": file.type,
          },
        }),
        transformErrorResponse: (error, _, { file }) =>
          transformErrorMessage(
            error,
            `${ERROR_MESSAGES.POST_FILE} ${file.name}`,
          ),
        onQueryStarted: async ({ file }, { dispatch, queryFulfilled }) => {
          await handleOnQueryStarted(
            queryFulfilled,
            dispatch,
            `${ERROR_MESSAGES.POST_FILE} ${file.name}`,
          );
        },
      }),
      deleteFile: builder.mutation({
        query: (url: string) => ({
          url,
          method: "DELETE",
        }),
        transformErrorResponse: (error) =>
          transformErrorMessage(error, ERROR_MESSAGES.DELETE_FILE),
        onQueryStarted: async (_, { dispatch, queryFulfilled }) => {
          await handleOnQueryStarted(
            queryFulfilled,
            dispatch,
            ERROR_MESSAGES.DELETE_FILE,
          );
        },
      }),
    }),
  });

  const { usePostFileMutation, useDeleteFileMutation } = s3Api;

  return { s3Api, usePostFileMutation, useDeleteFileMutation };
};
