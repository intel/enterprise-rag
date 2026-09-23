// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { keycloakService } from "@intel-enterprise-rag-ui/auth";
import { App } from "@intel-enterprise-rag-ui/layouts";

import AppRouter from "@/app/router";
import { store } from "@/store";

const AudioQnAApp = () => (
  <App store={store} router={<AppRouter />} keycloakService={keycloakService} />
);

export default AudioQnAApp;
