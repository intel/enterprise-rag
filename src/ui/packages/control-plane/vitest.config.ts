// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { fileURLToPath } from "node:url";

import { dirname, resolve } from "path";
import { defineConfig } from "vitest/config";

const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      "@/": `${resolve(__dirname, "./src")}/`,
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
