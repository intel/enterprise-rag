// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { NamespaceStatus } from "@/types/api/namespaceStatus";
import type { FetchedServicesData } from "@/types/api/services";

export type GetServicesDataResponse = FetchedServicesData;

export type GetServicesDetailsResponse = NamespaceStatus;

// One stored parameter group returned by the per-key config read. The values
// come back in wire shape: a flat kind carries its fields at the top level, a
// nested guard kind carries them under its dedicated key.
export interface GetServiceConfigResponse {
  params_key: string;
  params_kind: string;
  version: number;
  values: Record<string, unknown>;
}

export interface AppendArgumentsParameters {
  max_new_tokens: number;
  // Only present in the docsum group; optional so non-docsum groups do not
  // have to carry it.
  summary_type?: string;
  top_k: number;
  top_p: number;
  typical_p: number;
  temperature: number;
  repetition_penalty: number;
  stream: boolean;
  search_type: string;
  k: number;
  distance_threshold: number | null;
  fetch_k: number;
  lambda_mult: number;
  score_threshold: number;
  rerank_score_threshold: number | null;
  top_n: number;
  metadata_extraction_mode: string | null;
  user_prompt_template: string;
  system_prompt_template: string;
  input_guardrail_params: {
    [key: string]: {
      [key: string]: string | number | boolean | string[] | undefined | null;
    };
  };
  output_guardrail_params: {
    [key: string]: {
      [key: string]: string | number | boolean | string[] | undefined | null;
    };
  };
}
