// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Middleware } from "@reduxjs/toolkit";

import { edpApi } from "@/api/edpApi";

export const createDataIngestionApiMiddleware =
  (deleteFileMatchFulfilled: (action: unknown) => boolean): Middleware =>
  (middlewareApi) =>
  (next) =>
  (action) => {
    const result = next(action);

    if (deleteFileMatchFulfilled(action)) {
      middlewareApi.dispatch(edpApi.util.invalidateTags(["Files"]));
    }

    return result;
  };
