// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  ServiceArgumentCheckboxValue,
  ServiceArgumentInputValue,
  ServiceArgumentNumberInputValue,
  ServiceArgumentSelectInputValue,
} from "@/types/index";

export const summaryTypes = ["map_reduce", "refine", "stuff"] as const;

export type SummaryType = (typeof summaryTypes)[number];

export const docsumFormConfig = {
  summary_type: {
    name: "summary_type",
    options: [...summaryTypes],
    tooltipText:
      "How the documents are combined into a summary. 'map_reduce' summarizes each chunk then combines the results, 'refine' iteratively updates a running summary chunk by chunk, and 'stuff' sends the whole input in a single call.",
  },
  max_new_tokens: {
    name: "max_new_tokens",
    range: { min: 1, max: 2048 },
  },
  stream: {
    name: "stream",
  },
};

export const docsumArgumentsDefault: DocsumArgs = {
  summary_type: "map_reduce",
  max_new_tokens: null,
  stream: true,
};

export interface DocsumArgs extends Record<string, ServiceArgumentInputValue> {
  summary_type: ServiceArgumentSelectInputValue;
  max_new_tokens: ServiceArgumentNumberInputValue;
  stream: ServiceArgumentCheckboxValue;
}
