// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { getAppEnv } from "@intel-enterprise-rag-ui/utils";

// Tenant dimension of the fingerprint config scope. Held at the shared default
// until per-user tenants land behind FINGERPRINT_PER_USER_TENANT.
const TENANT = "_global";

/**
 * Reads the deployed pipeline the UI represents, injected as runtime env so the
 * value follows the deployment rather than a build. Returns an empty string when
 * unset.
 * @returns {string} The pipeline name, or "" when no PIPELINE env is present.
 */
const getPipeline = (): string => {
  const windowObj = typeof window !== "undefined" ? window : undefined;
  return getAppEnv(import.meta.env, windowObj, "PIPELINE");
};

/**
 * Builds a fingerprint config URL that addresses the UI's own pipeline scope.
 * Appends pipeline and tenant so a read or write reaches the pipeline the UI
 * represents instead of the fingerprint service default. When the PIPELINE env
 * is absent the scope is omitted and only extraParams remain, preserving the
 * unscoped request other callers made before.
 * @param {string} endpoint - The base fingerprint config endpoint.
 * @param {Record<string, string>} [extraParams] - Query params to keep, e.g. params_key.
 * @returns {string} The endpoint with query string, or bare endpoint when neither scope nor params apply.
 */
export const withScope = (
  endpoint: string,
  extraParams?: Record<string, string>,
): string => {
  const params = new URLSearchParams(extraParams);

  const pipeline = getPipeline();
  if (pipeline) {
    params.set("pipeline", pipeline);
    params.set("tenant", TENANT);
  }

  const query = params.toString();
  return query ? `${endpoint}?${query}` : endpoint;
};
