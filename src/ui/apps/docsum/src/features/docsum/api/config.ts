// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export const DOCSUM_API_ENDPOINTS = {
  BASE_URL: "/api/v1/docsum",
};

export const ERROR_MESSAGES = {
  SUMMARIZE_TEXT: "Failed to summarize text.",
  SUMMARIZE_FILE: "Failed to summarize file.",
};

// Backend/gateway error bodies can be long and technical (e.g. exact token
// counts, internal step names) — fine for the Network tab, too much for a
// toast. These statuses always get a short, consistent message instead.
const TIMEOUT_MESSAGE =
  "Your request took too long to process. Please try a shorter input or a different summary type.";
const SERVICE_UNAVAILABLE_MESSAGE =
  "The summarization service is temporarily unavailable. Please try again later.";

export const HTTP_ERRORS = {
  BAD_REQUEST: {
    statusCode: 400,
    errorMessage:
      "The input couldn't be processed. Try a shorter document or a different summary type.",
  },
  NOT_FOUND: {
    statusCode: 404,
    errorMessage:
      "Couldn't reach the summarization service. Please try again in a moment.",
  },
  // The LLM microservice's own read-timeout on a single call — distinct from
  // GATEWAY_TIMEOUT below, which is the reverse proxy timing out the whole request.
  REQUEST_TIMEOUT: {
    statusCode: 408,
    errorMessage: TIMEOUT_MESSAGE,
  },
  TOO_MANY_REQUESTS: {
    statusCode: 429,
    errorMessage: "Too many requests. Please try again later.",
  },
  INTERNAL_SERVER_ERROR: {
    statusCode: 500,
    errorMessage: "Something went wrong while summarizing. Please try again.",
  },
  NOT_IMPLEMENTED: {
    statusCode: 501,
    errorMessage:
      "This action isn't supported by the current configuration. Please contact your administrator.",
  },
  BAD_GATEWAY: {
    statusCode: 502,
    errorMessage: SERVICE_UNAVAILABLE_MESSAGE,
  },
  SERVICE_UNAVAILABLE: {
    statusCode: 503,
    errorMessage: SERVICE_UNAVAILABLE_MESSAGE,
  },
  GATEWAY_TIMEOUT: {
    statusCode: 504,
    errorMessage: TIMEOUT_MESSAGE,
  },
} as const;
