// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { SummaryType, SummaryUpdateHandler } from "@/features/docsum/api/types";

const buildFileUploadFormData = (
  file: File,
  summaryType?: SummaryType,
): FormData => {
  const formData = new FormData();
  formData.append("files", file, file.name);
  if (summaryType) {
    formData.append(
      "parameters",
      JSON.stringify({ summary_type: summaryType }),
    );
  }
  return formData;
};

const parseOpenAIChunk = (chunk: string) => {
  try {
    const parsed = JSON.parse(chunk);
    const content = parsed?.choices?.[0]?.delta?.content;
    return typeof content === "string" ? content : null;
  } catch {
    return null;
  }
};

const handleSummaryStreamResponse = async (
  response: Response,
  onSummaryUpdate: SummaryUpdateHandler,
) => {
  const reader = response.body?.getReader();
  const decoder = new TextDecoder("utf-8");

  if (!reader) return;

  let done = false;
  do {
    const result = await reader.read();
    done = result?.done ?? true;

    if (result?.value) {
      const decodedValue = decoder.decode(result.value, { stream: true });

      const events = decodedValue.split("\n\n");

      for (const event of events) {
        if (event.startsWith("data:")) {
          // skip to the next iteration if event data message is a keyword indicating that stream has finished
          if (event.includes("[DONE]") || event.includes("</s>")) {
            continue;
          }

          // extract chunk of text from event data message
          const dataChunk = event.slice(6).trimStart();
          const openAiChunk = parseOpenAIChunk(dataChunk);

          if (openAiChunk !== null) {
            onSummaryUpdate(openAiChunk);
            continue;
          }

          const newTextChunk = dataChunk
            .replace(/\\t/g, "  \t")
            .replace(/\\n\\n/g, "  \n\n")
            .replace(/\\n/g, "  \n");

          onSummaryUpdate(newTextChunk);
        }
      }
    }
  } while (!done);
};

const transformResponseError = (response: Response) => ({
  error: {
    status: response.status,
    data: `Error ${response.status}: ${response.statusText}`,
  },
});

export {
  buildFileUploadFormData,
  handleSummaryStreamResponse,
  transformResponseError,
};
