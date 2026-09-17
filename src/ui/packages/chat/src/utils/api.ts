// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { SerializedError } from "@reduxjs/toolkit";
import { FetchBaseQueryError } from "@reduxjs/toolkit/query/react";

import {
  ABORT_ERROR_MESSAGE,
  DEFAULT_ERROR_MESSAGE,
  HTTP_ERRORS,
} from "@/api/config";
import {
  AnswerUpdateHandler,
  ChatErrorResponse,
  SourcesUpdateHandler,
} from "@/types/api";

export const handleChatJsonResponse = async (
  response: Response,
  onAnswerUpdate: AnswerUpdateHandler,
  onSourcesUpdate: SourcesUpdateHandler,
) => {
  const json = await response.json();
  onAnswerUpdate(json.text);
  onSourcesUpdate(json.json.reranked_docs || []);
};

const EVENT_SEPARATOR = "\n\n";

// Payloads a backend sends as its own frame to close the stream.
const STREAM_TERMINATORS = new Set(["[DONE]", "</s>"]);

const handleStreamEvent = (
  event: string,
  onAnswerUpdate: AnswerUpdateHandler,
  onSourcesUpdate: SourcesUpdateHandler,
) => {
  if (event.startsWith("data:")) {
    // extract chunk of text from event data message
    const dataContent = event.slice(5).trim();

    // The backends close the stream with a dedicated terminator frame, so match
    // the payload exactly: a substring test would also drop a frame whose answer
    // text happens to contain the marker.
    if (STREAM_TERMINATORS.has(dataContent)) {
      return;
    }

    try {
      // Parse OpenAI-style streaming JSON format
      const chunkData = JSON.parse(dataContent);

      if (chunkData.choices && chunkData.choices[0]?.delta?.content) {
        const newTextChunk = chunkData.choices[0].delta.content;
        onAnswerUpdate(newTextChunk);
      }
    } catch {
      // Fallback: treat as plain text if JSON parsing fails
      let newTextChunk = dataContent;
      let quoteRegex = /(?<!\\)'/g;
      if (newTextChunk.startsWith('"')) {
        quoteRegex = /"/g;
      }
      newTextChunk = newTextChunk
        .replace(quoteRegex, "")
        .replace(/\\t/g, "  \t")
        .replace(/\\n/g, "  \n");

      onAnswerUpdate(newTextChunk);
    }
  }

  // handling JSON data event for reranked documents aka sources
  if (event.startsWith("json:")) {
    const jsonText = event.slice(5).trim();
    try {
      const sourcesDataObject = JSON.parse(jsonText);
      const rerankedDocs = sourcesDataObject.reranked_docs || [];
      onSourcesUpdate(rerankedDocs);
    } catch (error) {
      // Keep whatever sources were already shown: a frame we cannot read is not
      // evidence that the answer has no sources.
      console.error("Error parsing JSON data:", error);
    }
  }
};

export const handleChatStreamResponse = async (
  response: Response,
  onAnswerUpdate: AnswerUpdateHandler,
  onSourcesUpdate: SourcesUpdateHandler,
) => {
  const reader = response.body?.getReader();
  const decoder = new TextDecoder("utf-8");

  // An event is only complete once its "\n\n" terminator arrives, and a read can
  // end mid-event: the sources frame carries every reranked document, so it is
  // large enough to straddle reads. Anything after the last terminator is held
  // back and prefixed onto the next read instead of being parsed truncated.
  let buffer = "";

  let done = false;
  do {
    const result = await reader?.read();
    done = result?.done ?? true;
    if (done) break;

    buffer += decoder.decode(result?.value, { stream: true });

    // in case of streaming multiple events at one time - configuration with output guard
    const events = buffer.split(EVENT_SEPARATOR);
    // The trailing element is either an incomplete event or "" when the buffer
    // ended exactly on a separator; both are correct to carry over.
    buffer = events.pop() ?? "";

    for (const event of events) {
      handleStreamEvent(event, onAnswerUpdate, onSourcesUpdate);
    }
  } while (!done);

  // Flush a final event that arrived without a trailing separator.
  buffer += decoder.decode();
  if (buffer.length > 0) {
    handleStreamEvent(buffer, onAnswerUpdate, onSourcesUpdate);
  }
};

export const createGuardrailsErrorResponse = async (response: Response) => {
  const errorData = await response.json();
  const guardrailsErrorResponse = {} as ChatErrorResponse;
  guardrailsErrorResponse.data = errorData;
  return guardrailsErrorResponse;
};

export const transformChatErrorResponse = (
  error: FetchBaseQueryError,
): Pick<ChatErrorResponse, "status" | "data"> => {
  const responseError = error as ChatErrorResponse;

  if (isAbortResponseError(responseError)) {
    return {
      status: HTTP_ERRORS.CLIENT_CLOSED_REQUEST.statusCode,
      data: HTTP_ERRORS.CLIENT_CLOSED_REQUEST.errorMessage,
    };
  }

  const statusCode = responseError.originalStatus || responseError.status;

  switch (statusCode) {
    case HTTP_ERRORS.REQUEST_TIMEOUT.statusCode:
      return {
        status: HTTP_ERRORS.REQUEST_TIMEOUT.statusCode,
        data: HTTP_ERRORS.REQUEST_TIMEOUT.errorMessage,
      };
    case HTTP_ERRORS.PAYLOAD_TOO_LARGE.statusCode:
      return {
        status: HTTP_ERRORS.PAYLOAD_TOO_LARGE.statusCode,
        data: HTTP_ERRORS.PAYLOAD_TOO_LARGE.errorMessage,
      };
    case HTTP_ERRORS.TOO_MANY_REQUESTS.statusCode:
      return {
        status: HTTP_ERRORS.TOO_MANY_REQUESTS.statusCode,
        data: HTTP_ERRORS.TOO_MANY_REQUESTS.errorMessage,
      };
    case HTTP_ERRORS.GUARDRAILS_ERROR.statusCode:
      return {
        status: HTTP_ERRORS.GUARDRAILS_ERROR.statusCode,
        data: parseGuardrailsResponseErrorDetail(responseError),
      };
    default:
      return {
        status: statusCode,
        data: parseUserMessage(responseError) ?? DEFAULT_ERROR_MESSAGE,
      };
  }
};

const isAbortResponseError = (errorResponse: ChatErrorResponse) => {
  const isFetchAbortError =
    errorResponse.status === "FETCH_ERROR" &&
    errorResponse.error === ABORT_ERROR_MESSAGE;
  const containsBrowserAbortMessage =
    typeof errorResponse.error === "string" &&
    (errorResponse.error.toLowerCase().includes("abort") ||
      errorResponse.error.toLowerCase().includes("interrupt") ||
      errorResponse.error === "AbortError: BodyStreamBuffer was aborted" || // Edge & Chrome
      errorResponse.error === "User interrupted chatbot response."); // Firefox
  const isParsingAbortError =
    errorResponse.status === "PARSING_ERROR" &&
    errorResponse.originalStatus === 200 &&
    containsBrowserAbortMessage;
  return isFetchAbortError || isParsingAbortError;
};

const parseUserMessage = (responseError: ChatErrorResponse): string | null => {
  try {
    const data = isChatErrorResponseDataString(responseError.data)
      ? JSON.parse(responseError.data)
      : responseError.data;

    if (data && typeof data.user_message === "string") {
      return data.user_message;
    }
    return null;
  } catch {
    return null;
  }
};

const parseGuardrailsResponseErrorDetail = (
  responseError: ChatErrorResponse,
) => {
  try {
    if (!isChatErrorResponseDataString(responseError.data)) {
      return HTTP_ERRORS.GUARDRAILS_ERROR.parsingErrorMessages.INVALID_FORMAT;
    }

    const parsedResponseData = JSON.parse(responseError.data);

    if (!parsedResponseData.error) {
      return HTTP_ERRORS.GUARDRAILS_ERROR.parsingErrorMessages.MISSING_ERROR;
    } else if (typeof parsedResponseData.error !== "string") {
      return HTTP_ERRORS.GUARDRAILS_ERROR.parsingErrorMessages
        .INVALID_ERROR_FORMAT;
    }

    const errorObj = JSON.parse(parsedResponseData.error);
    return (
      errorObj.detail ||
      HTTP_ERRORS.GUARDRAILS_ERROR.parsingErrorMessages.UNKNOWN
    );
  } catch {
    return HTTP_ERRORS.GUARDRAILS_ERROR.parsingErrorMessages.PARSING_FAILED;
  }
};

export const isChatErrorResponse = (
  error?: FetchBaseQueryError | SerializedError,
): error is ChatErrorResponse =>
  error !== null &&
  typeof error === "object" &&
  "status" in error &&
  "data" in error;

export const isChatErrorResponseDataString = (data: unknown): data is string =>
  typeof data === "string";
