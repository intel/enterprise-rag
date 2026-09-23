// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";

import {
  assembleServicesParameters,
  parseServiceParametersByKind,
} from "@/utils/api";

describe("parseServiceParametersByKind", () => {
  it("reads a flat kind's values bare", () => {
    const values = {
      max_new_tokens: 512,
      top_k: 10,
      top_p: 0.95,
      typical_p: 0.95,
      temperature: 0.2,
      repetition_penalty: 1.1,
      stream: true,
    };

    const parsed = parseServiceParametersByKind("llm", values);

    expect(parsed).toEqual({ llmArgs: values });
  });

  it("reads a nested guard kind from its wire-shaped fragment", () => {
    const scanners = {
      prompt_injection: { enabled: true, threshold: 0.9, match_type: "full" },
    };
    const values = { input_guardrail_params: scanners };

    const parsed = parseServiceParametersByKind("input_guard", values);

    expect(parsed).toEqual({ inputGuardArgs: scanners });
  });

  it("reads the docsum flat kind's values as its card args", () => {
    const values = {
      summary_type: "refine",
      max_new_tokens: 512,
      stream: false,
    };

    const parsed = parseServiceParametersByKind("docsum", values);

    expect(parsed).toEqual({ docsumArgs: values });
  });

  it("falls back to the docsum defaults when a field is absent", () => {
    // A stored docsum row (or the service default) that omits fields must not
    // hydrate the card with undefined; the microservice defaults fill the gaps.
    const parsed = parseServiceParametersByKind("docsum", {});

    expect(parsed).toEqual({
      docsumArgs: {
        summary_type: "map_reduce",
        max_new_tokens: 1024,
        stream: true,
      },
    });
  });

  it("returns no args for an unknown kind", () => {
    const parsed = parseServiceParametersByKind("mystery", { foo: "bar" });

    expect(parsed).toEqual({});
  });
});

describe("assembleServicesParameters", () => {
  it("merges per-key groups into one card-args set", () => {
    const llmValues = {
      max_new_tokens: 512,
      top_k: 10,
      top_p: 0.95,
      typical_p: 0.95,
      temperature: 0.2,
      repetition_penalty: 1.1,
      stream: true,
    };
    const scanners = {
      prompt_injection: { enabled: true, threshold: 0.9, match_type: "full" },
    };

    const parameters = assembleServicesParameters([
      { params_kind: "llm", values: llmValues },
      {
        params_kind: "input_guard",
        values: { input_guardrail_params: scanners },
      },
    ]);

    expect(parameters.llmArgs).toEqual(llmValues);
    expect(parameters.inputGuardArgs).toEqual(scanners);
  });

  it("assembles the docsum pipeline's llm and docsum groups", () => {
    const llmValues = {
      max_new_tokens: 1024,
      top_k: 10,
      top_p: 0.95,
      typical_p: 0.95,
      temperature: 0.01,
      repetition_penalty: 1.03,
      stream: true,
    };
    const docsumValues = {
      summary_type: "map_reduce",
      max_new_tokens: 1024,
      stream: true,
    };

    const parameters = assembleServicesParameters([
      { params_kind: "llm", values: llmValues },
      { params_kind: "docsum", values: docsumValues },
    ]);

    expect(parameters.llmArgs).toEqual(llmValues);
    expect(parameters.docsumArgs).toEqual(docsumValues);
  });

  it("leaves a card's args unset when its group is absent", () => {
    const parameters = assembleServicesParameters([
      {
        params_kind: "reranker",
        values: { top_n: 3, rerank_score_threshold: 0.5 },
      },
    ]);

    expect(parameters.rerankerArgs).toEqual({
      top_n: 3,
      rerank_score_threshold: 0.5,
    });
    expect(parameters.llmArgs).toBeUndefined();
  });
});
