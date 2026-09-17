// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { keycloakService } from "@intel-enterprise-rag-ui/auth";
import { FetchBaseQueryError } from "@reduxjs/toolkit/query/react";

import { HTTP_ERRORS } from "@/features/docsum/api/config";
import { resetStore } from "@/store/utils";

// Backends in this pipeline report user-facing errors as a `user_message`
// field (e.g. DocSum's context-length error), whether the body already
// arrived as an object or as a JSON string that still needs parsing.
const parseUserMessage = (data: unknown): string | null => {
  try {
    const parsed: unknown = typeof data === "string" ? JSON.parse(data) : data;
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      "user_message" in parsed &&
      typeof (parsed as { user_message: unknown }).user_message === "string"
    ) {
      return (parsed as { user_message: string }).user_message;
    }
    return null;
  } catch {
    return null;
  }
};

const getErrorMessage = (error: unknown, fallbackMessage: string): string => {
  if (typeof error !== "object" || error === null) {
    return fallbackMessage;
  }

  const fetchError = error as FetchBaseQueryError;

  // A custom `responseHandler` that rejects doesn't surface as a plain
  // `{status: number}` error — RTK Query wraps it as PARSING_ERROR, moving the
  // real HTTP status to `originalStatus` and the response body to `data`
  // (read independently via its own `response.clone().text()`, so it's intact
  // regardless of what the responseHandler rejected with).
  const statusCode =
    typeof fetchError.status === "number"
      ? fetchError.status
      : "originalStatus" in fetchError &&
          typeof fetchError.originalStatus === "number"
        ? fetchError.originalStatus
        : undefined;

  const knownError = Object.values(HTTP_ERRORS).find(
    ({ statusCode: code }) => code === statusCode,
  );
  if (knownError) {
    return knownError.errorMessage;
  }

  if ("data" in fetchError) {
    const userMessage = parseUserMessage(fetchError.data);
    if (userMessage) {
      return userMessage;
    }

    if (typeof fetchError.data === "string" && fetchError.data) {
      return fetchError.data;
    }

    if (typeof fetchError.data === "object" && fetchError.data !== null) {
      if (
        "message" in fetchError.data &&
        typeof fetchError.data.message === "string"
      ) {
        return fetchError.data.message;
      } else if (
        "detail" in fetchError.data &&
        typeof fetchError.data.detail === "string"
      ) {
        return fetchError.data.detail;
      }
    }
  }

  if ("error" in fetchError && typeof fetchError.error === "string") {
    return fetchError.error;
  }

  return fallbackMessage;
};

const onRefreshTokenFailed = () => {
  keycloakService.redirectToLogout();
  resetStore();
};

const transformErrorMessage = (
  error: FetchBaseQueryError,
  fallbackMessage: string,
): FetchBaseQueryError => {
  if (error.status === "FETCH_ERROR") {
    return { ...error, error: fallbackMessage };
  } else {
    return error;
  }
};

export { getErrorMessage, onRefreshTokenFailed, transformErrorMessage };
