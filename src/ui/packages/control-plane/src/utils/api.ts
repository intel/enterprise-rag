// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { LLMInputGuardArgs } from "@/configs/guards/llmInputGuard";
import { LLMOutputGuardArgs } from "@/configs/guards/llmOutputGuard";
import { SummaryType } from "@/configs/services/docsum";
import {
  MetadataExtractionMode,
  RetrieverSearchType,
} from "@/configs/services/retriever";
import {
  AppendArgumentsParameters,
  GetServiceConfigResponse,
} from "@/types/api/responses";
import { FetchedServicesParameters } from "@/types/api/services";

// Canonical parameter groups the control plane hydrates as cards, each read per
// key from the scoped config route. Other stored groups (e.g. query_rewrite)
// have no card and are not fetched. This is the chatqa/audioqna set; a pipeline
// with a different set of tunable steps declares its own list (see
// DOCSUM_PARAMS_KEYS).
export const CONTROL_PLANE_PARAMS_KEYS = [
  "llm",
  "retriever",
  "reranker",
  "prompt_template",
  "input_guard",
  "output_guard",
] as const;

// Parameter groups the docsum pipeline hydrates as cards: its tunable LLM step
// and the docsum summarization step.
export const DOCSUM_PARAMS_KEYS = ["llm", "docsum"] as const;

/**
 * Merges the per-key groups returned by the scoped config reads into the single
 * card-args set the control plane renders. Each group is mapped by its kind, so
 * the groups can arrive in any order and a missing group simply leaves its card
 * args unset.
 */
export const assembleServicesParameters = (
  groups: Pick<GetServiceConfigResponse, "params_kind" | "values">[],
): FetchedServicesParameters =>
  groups.reduce<FetchedServicesParameters>(
    (parameters, { params_kind, values }) => ({
      ...parameters,
      ...parseServiceParametersByKind(params_kind, values),
    }),
    {},
  );

/**
 * Maps one stored parameter group, addressed by its kind, to the card args the
 * control plane renders. Used by the per-key read path so a single instance's
 * values (e.g. one of several LLM steps) hydrate its own card. The per-key read
 * returns a group's values already in wire shape: flat kinds carry their fields
 * at the top level, and nested guard kinds carry them under their dedicated key,
 * so the fragment is handed to the whole-blob parser unchanged. Unknown kinds
 * return no args.
 */
export const parseServiceParametersByKind = (
  paramsKind: string,
  values: Record<string, unknown>,
): FetchedServicesParameters => {
  const parsed = parseServicesParameters(
    values as unknown as AppendArgumentsParameters,
  );

  switch (paramsKind) {
    case "llm":
      return { llmArgs: parsed.llmArgs };
    case "retriever":
      return { retrieverArgs: parsed.retrieverArgs };
    case "reranker":
      return { rerankerArgs: parsed.rerankerArgs };
    case "prompt_template":
      return { promptTemplateArgs: parsed.promptTemplateArgs };
    case "input_guard":
      return { inputGuardArgs: parsed.inputGuardArgs };
    case "output_guard":
      return { outputGuardArgs: parsed.outputGuardArgs };
    case "docsum":
      return { docsumArgs: parsed.docsumArgs };
    default:
      return {};
  }
};

export const parseServicesParameters = (
  parameters: AppendArgumentsParameters,
): FetchedServicesParameters => {
  const {
    max_new_tokens,
    top_k,
    top_p,
    typical_p,
    temperature,
    repetition_penalty,
    stream,
    search_type,
    k,
    user_prompt_template,
    system_prompt_template,
    distance_threshold,
    fetch_k,
    lambda_mult,
    rerank_score_threshold,
    score_threshold,
    top_n,
    metadata_extraction_mode,
    input_guardrail_params,
    output_guardrail_params,
    summary_type,
  } = parameters;

  return {
    llmArgs: {
      max_new_tokens,
      top_k,
      top_p,
      typical_p,
      temperature,
      repetition_penalty,
      stream,
    },
    retrieverArgs: {
      search_type: search_type as RetrieverSearchType,
      k,
      distance_threshold,
      fetch_k,
      lambda_mult,
      score_threshold,
      metadata_extraction_mode: (metadata_extraction_mode ??
        "off") as MetadataExtractionMode,
    },
    rerankerArgs: { top_n, rerank_score_threshold },
    promptTemplateArgs: {
      user_prompt_template,
      system_prompt_template,
    },
    inputGuardArgs: input_guardrail_params as LLMInputGuardArgs,
    outputGuardArgs: output_guardrail_params as LLMOutputGuardArgs,
    docsumArgs: {
      // An incomplete stored group can omit these fields, so fall back to the
      // docsum microservice defaults to keep the card in a valid state. The
      // fallback matters most for summary_type, which feeds a select input that
      // renders no value (and cannot be submitted) when hydrated with undefined.
      // The other kinds map only to text/number inputs that tolerate undefined,
      // so their branches need no fallback.
      summary_type: (summary_type ?? "map_reduce") as SummaryType,
      max_new_tokens: max_new_tokens ?? 1024,
      stream: stream ?? true,
    },
  };
};
